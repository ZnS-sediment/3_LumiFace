#!/usr/bin/env python3
"""Split the 400-person archive by identity, preserving all bytes and queries."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def people(bundle):
    return {n.split('/')[-2] for n in bundle.namelist() if '/gallery/' in n and n.endswith('.png')}


def build(old_path, combined_path, destination):
    if destination.resolve() in {old_path.resolve(), combined_path.resolve()}:
        raise ValueError('Do not overwrite source downloads')
    staged = destination.with_suffix('.tmp.zip')
    with zipfile.ZipFile(old_path) as old, zipfile.ZipFile(combined_path) as source:
        previous, all_people = people(old), people(source)
        assert len(previous) == 120 and len(all_people) == 400 and previous <= all_people
        selected = all_people - previous
        assert len(selected) == 280 and not previous & selected
        prefix = 'lfw_280_new_lighting/'
        protocol = json.loads(source.read('lfw_400_lighting/protocol.json'))
        protocol.update(persons=280, gallery_images=560, query_images_per_scene=840,
            identity_selection='All 400-person package identities except the original 120. No query-performance filtering.',
            excluded_identity_count=120, excluded_identities=sorted(previous),
            identity_labels=sorted(selected),
            source_archive_sha256=hashlib.sha256(combined_path.read_bytes()).hexdigest(),
            original_archive_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest())
        records = json.loads(source.read('lfw_400_lighting/provenance.json'))
        records = [r for r in records if r['file'].split('/')[-2] in selected]
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED) as output:
            for name in source.namelist():
                if name.endswith('.png') and ('/gallery/' in name or '/query/' in name) and name.split('/')[-2] in selected:
                    output.writestr(prefix + name.split('/', 1)[1], source.read(name))
            output.writestr(prefix+'protocol.json', json.dumps(protocol, ensure_ascii=False, indent=2))
            output.writestr(prefix+'provenance.json', json.dumps(records, ensure_ascii=False, indent=2))
            output.writestr(prefix+'使用说明.txt',
                '新增 280 人身份与光照数据包\n\n本包与原 120 人包没有重复身份。\n'
                'gallery：280 人，每人 2 张注册图，共 560 张。\n'
                'query：正常光照、逆光、光照不均、低照度各 840 张，每人每场景 3 张。\n'
                '注册 gallery 后，测试时选择 query 下的一个场景目录。可以和原 120 人同时注册。\n'
                '注册图与查询图来自不同源照片；不同光照变体属于同源查询图。\n'
                '三类特殊光照为软件模拟，不能作为红外实采或实景性能验收；全部查询图保留，不按正确率挑选。\n'
                '数据源与固定裁剪方式见 protocol.json，文件校验和见 provenance.json。LFW 来源图片版权属于原权利人，仅用于本地课程研究演示。')
    with zipfile.ZipFile(staged) as result:
        assert result.testzip() is None
        assert people(result) == selected
        assert len([n for n in result.namelist() if '/gallery/' in n and n.endswith('.png')]) == 560
        assert len([n for n in result.namelist() if '/query/' in n and n.endswith('.png')]) == 3360
    staged.replace(destination)
    return protocol


if __name__ == '__main__':
    result = build(ROOT/'datasets/lfw_120_lighting.zip', ROOT/'datasets/lfw_400_lighting.zip', ROOT/'datasets/lfw_280_new_lighting.zip')
    print(json.dumps({k:result[k] for k in ['persons','gallery_images','query_images_per_scene','identity_selection']}, ensure_ascii=False, indent=2))
