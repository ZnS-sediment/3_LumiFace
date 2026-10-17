import io
import json
import shutil
import uuid
import zipfile
from pathlib import PurePosixPath
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import DATA, MAX_ARCHIVE, MAX_UPLOAD
from app.core.errors import AppError
from app.models.entities import Dataset, FaceSample, Person
from app.schemas.contracts import Manifest
from app.services.images import decode, digest, png


def import_dataset(db: Session, raw: bytes) -> Dataset:
    if len(raw) > MAX_ARCHIVE:
        raise AppError('ZIP 压缩包不得超过 100 MB', 413)
    directory = DATA / 'datasets' / uuid.uuid4().hex
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [m.filename for m in members]
            if len(members) > 1001 or len(names) != len(set(names)):
                raise AppError('ZIP 文件数量超限或含重名条目')
            if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n or ':' in n for n in names):
                raise AppError('ZIP 含非法路径')
            if sum(m.file_size for m in members) > 256 * 1024 * 1024:
                raise AppError('ZIP 解压总量不得超过 256 MB', 413)
            if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size > 2 * 1024 * 1024:
                raise AppError('ZIP 根目录须包含不超过 2 MB 的 manifest.json')
            manifest = Manifest.model_validate_json(archive.read('manifest.json'))
            if len({x.file for x in manifest.items}) != len(manifest.items):
                raise AppError('manifest 中存在重复文件')
            persons = list(db.scalars(select(Person)))
            known = {p.id for p in persons}
            references = {str(p.id): p.created_at.replace(tzinfo=None).isoformat() for p in persons}
            samples = list(db.scalars(select(FaceSample)))
            forbidden_hashes = {s.digest for s in samples}
            forbidden_captures = {s.capture_id for s in samples}
            other_unknowns = set()
            for prior in db.scalars(select(Dataset)):
                if prior.split != manifest.split:
                    forbidden_hashes.update(x['digest'] for x in prior.manifest['items'])
                    forbidden_captures.update(x['capture_id'] for x in prior.manifest['items'])
                    other_unknowns.update(f['subject'] for x in prior.manifest['items'] for f in x['faces'] if f['person_id'] is None)
            directory.mkdir(mode=0o700)
            items = []
            for index, item in enumerate(manifest.items):
                if item.file not in names or archive.getinfo(item.file).file_size > MAX_UPLOAD:
                    raise AppError(f'图片缺失或超过 12 MB：{item.file}')
                image = decode(archive.read(item.file))
                image_hash = digest(image)
                if image_hash in forbidden_hashes or item.capture_id in forbidden_captures:
                    raise AppError(f'{item.file} 与注册/其他数据划分存在图像或采集会话泄漏', 409)
                forbidden_hashes.add(image_hash)
                if manifest.localization_protocol == 'single_face_presence' and len(item.faces) != 1:
                    raise AppError('单人脸存在性协议须每图恰有一个身份标注')
                for face in item.faces:
                    if manifest.localization_protocol == 'eye_containment' and face.eyes is None:
                        raise AppError('眼点包含协议需要独立眼点标注')
                    if face.eyes and any(not (0 <= x < image.shape[1] and 0 <= y < image.shape[0]) for x, y in face.eyes):
                        raise AppError('眼点坐标超出图像尺寸')
                    if face.person_id is not None and face.person_id not in known:
                        raise AppError(f'未知 person_id：{face.person_id}')
                    if face.person_id is None and face.subject in other_unknowns:
                        raise AppError('校准与测试的未知身份必须互斥', 409)
                    if face.bbox[2] > image.shape[1] or face.bbox[3] > image.shape[0]:
                        raise AppError(f'{item.file} 的标注框超出经 EXIF 纠正后的图像尺寸')
                filename = f'{index}.png'
                (directory / filename).write_bytes(png(image))
                (directory / filename).chmod(0o600)
                items.append({**item.model_dump(), 'stored_file': filename, 'digest': image_hash})
            record = Dataset(name=manifest.name, split=manifest.split, directory=directory.name,
                             manifest={**manifest.model_dump(), 'items': items,
                                       'person_references': {str(f.person_id): references[str(f.person_id)]
                                                             for item in manifest.items for f in item.faces if f.person_id is not None}})
            db.add(record)
            db.commit()
            return record
    except AppError:
        db.rollback()
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, KeyError, ValidationError, ValueError, RuntimeError) as exc:
        db.rollback()
        shutil.rmtree(directory, ignore_errors=True)
        raise AppError(f'无效数据包：{exc}') from exc
    except Exception:
        db.rollback()
        shutil.rmtree(directory, ignore_errors=True)
        raise


def dataset_view(record: Dataset, detail: bool = False) -> dict:
    scenes = {}
    for item in record.manifest['items']:
        scenes[item['scene']] = scenes.get(item['scene'], 0) + 1
    result = {'id': record.id, 'name': record.name, 'split': record.split, 'count': len(record.manifest['items']),
              'scenes': scenes, 'real_capture': record.manifest['real_capture'], 'source': record.manifest['source'], 'license': record.manifest['license']}
    if detail:
        result['items'] = [{k: v for k, v in item.items() if k != 'stored_file'} for item in record.manifest['items']]
    return result
