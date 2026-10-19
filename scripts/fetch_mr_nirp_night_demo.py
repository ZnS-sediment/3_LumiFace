#!/usr/bin/env python3
"""Fetch four fixed public MR-NIRP NIR frames with bounded HTTP Range requests.
This is a one-person demo, not target validation. No full multi-GB archives are downloaded.
"""

import io, urllib.request, zipfile, json, hashlib
from pathlib import Path


class RemoteZip(io.RawIOBase):
    def __init__(self, url, size):
        self.url = url
        self.size = size
        self.pos = 0
        self.cache = {}
        self.transferred = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (
            offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        )
        return self.pos

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.pos
        size = min(size, self.size - self.pos)
        if size <= 0:
            return b""
        start = self.pos
        if size < 65536:
            a = start // 65536 * 65536
            b = min(self.size, max(a + 65536, start + size))
        else:
            a = start
            b = start + size
        key = (a, b)
        if key not in self.cache:
            if b - a > 16 * 1024 * 1024 or self.transferred + b - a > 32 * 1024 * 1024:
                raise ValueError("metadata/sample transfer budget exceeded")
            req = urllib.request.Request(
                self.url + "&segment=" + str(a) + "-" + str(b - 1),
                headers={"Range": f"bytes={a}-{b - 1}", "User-Agent": "LumiFace-Research/1.0"},
            )
            with urllib.request.urlopen(req, timeout=25) as response:
                expected = f"bytes {a}-{b - 1}/{self.size}"
                if response.status != 206 or response.headers.get("Content-Range") != expected:
                    raise ValueError("Server did not honor bounded Range request")
                data = response.read(b - a + 1)
            if len(data) != b - a:
                raise ValueError("Short response")
            self.cache[key] = data
            self.transferred += len(data)
        data = self.cache[key][start - a : start - a + size]
        self.pos += len(data)
        return data


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "datasets/raw/mr-nirp-night-sample"
OUT = ROOT / "datasets/mr_nirp_night_demo"
OFFICIAL = "https://computationalimaging.rice.edu/mr-nirp-dataset/"
SOURCES = [
    {
        "id": "1mI9rIKvcL2QiNXCCFq1KjKDJqOsbszDt",
        "size": 4201299210,
        "sequence": "subject16_driving_still_940",
        "role": "query",
        "frames": [
            (
                "NIR/Frame00001.pgm",
                "01-Frame00001.pgm",
                "f7435f251b769b655980f9bc35203012ab3d01c0a452a46662555fa8023b61d4",
            ),
            (
                "NIR/Frame03608.pgm",
                "02-Frame03608.pgm",
                "0e927f9dd6608a7521ee5587ac2aa65060e42ba9b5f602f77a7661f87857393f",
            ),
            (
                "NIR/Frame07215.pgm",
                "03-Frame07215.pgm",
                "2290dafc8467b7a5dd47608b5aae67f8952a4e282c668493aa3223df7310f2ca",
            ),
        ],
    },
    {
        "id": "1w3Ixg9_o25IoG1v1hfPOBf_gWBFzVsGB",
        "size": 3611462795,
        "sequence": "subject16_driving_small_motion_940",
        "role": "gallery",
        "frames": [
            (
                "NIR/Frame00001.pgm",
                "gallery-Frame00001.pgm",
                "507162d26a6997fa16fa0fd68e878cb8f03670a7c2f2fcd541d3ecebaa0a6368",
            )
        ],
    },
]


def main():
    import cv2
    import numpy as np

    RAW.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source in SOURCES:
        url = (
            "https://drive.usercontent.google.com/download?id="
            + source["id"]
            + "&export=download&confirm=t"
        )
        missing = [frame for frame in source["frames"] if not (RAW / frame[1]).exists()]
        if missing:
            reader = RemoteZip(url, source["size"])
            with zipfile.ZipFile(reader) as bundle:
                for member, name, expected in missing:
                    info = bundle.getinfo(member)
                    if info.file_size > 12 * 1024 * 1024 or info.compress_size > 12 * 1024 * 1024:
                        raise ValueError("Frame exceeds sample limits")
                    blob = bundle.read(info)
                    if hashlib.sha256(blob).hexdigest() != expected:
                        raise ValueError("Public sample changed; review source before continuing")
                    (RAW / name).write_bytes(blob)
        for member, name, expected in source["frames"]:
            blob = (RAW / name).read_bytes()
            if hashlib.sha256(blob).hexdigest() != expected:
                raise ValueError("Local raw sample hash mismatch: " + name)
            image = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_UNCHANGED)
            if image is None or image.dtype != np.uint16 or image.shape != (640, 640):
                raise ValueError("Unexpected raw frame format")
            image = np.rint(image.astype(np.float64) * 255 / 65535).clip(0, 255).astype(np.uint8)
            destination = OUT / source["role"] / "MRNIRP_002" / (Path(name).stem + ".png")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(destination), image):
                raise ValueError("PNG write failed")
            manifest.append(
                {
                    "file": str(destination.relative_to(OUT)),
                    "raw": name,
                    "raw_sha256": expected,
                    "png_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    "source_url": url,
                    "archive_bytes": source["size"],
                    "archive_sha256": None,
                    "source_member": member,
                    "sequence": source["sequence"],
                }
            )
    report = {
        "official_source": OFFICIAL,
        "documentation": "https://cpb-us-e1.wpmucdn.com/blogs.rice.edu/dist/3/6742/files/2021/01/MR-NIRP-Car_README.pdf",
        "citation": "Ewa M. Nowara, Tim K. Marks, Hassan Mansour, Ashok Veeraraghavan, Near-Infrared Imaging Photoplethysmography During Driving, IEEE TITS (2020).",
        "canonical_identity": "MR-NIRP Subject2 = Subject16; separate from all AT&T identities",
        "identities": 1,
        "gallery_images": 1,
        "query_images": 3,
        "sampling": "query fixed archive indices 0, floor(N/3), floor(2N/3); gallery first image of another recording; fixed before inference",
        "conversion": "uint16 to uint8: round(value*255/65535), identical fixed scaling for all frames; no AI relighting or local contrast edits",
        "capture_independence": "different recordings; independent visits not established",
        "target_validation": False,
        "files": manifest,
    }
    (OUT / "provenance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (OUT / "README.zh-CN.md").write_text(
        "MR-NIRP 真实夜间主动近红外功能样本\n\n来源："
        + OFFICIAL
        + "\n\n一人，1 张参考图、3 张查询图。MRNIRP_002 对应官方 Subject2/Subject16，是同一人，与 AT&T 身份不同。gallery 与 query 来自不同录像，不能据此声称独立会话验收。固定取样保留全部查询，包括不清晰帧，不按识别成绩筛选。\n\nWindows 解压后，在身份库批量导入时只选择 gallery；数据批次使用 mr-nirp-night-demo。查询时上传 query 内图像。该包不是实验评估页所需的标注 ZIP，没有独立校准或未知人员。\n\n本包仅作真实夜间图像处理和身份流程探索，不能验证 95%/90%/95% 三项目标。完整来源、引用、逐文件摘要和固定强度转换记录见 provenance.json。\n"
    )
    archive = ROOT / "datasets/mr_nirp_night_demo.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and path.name not in ("conversion.json",) and path.parent != OUT:
                bundle.write(path, "mr_nirp_night_demo/" + str(path.relative_to(OUT)))
        for name in ("provenance.json", "README.zh-CN.md"):
            bundle.write(OUT / name, "mr_nirp_night_demo/" + name)
    print(
        json.dumps(
            {
                "folder": str(OUT),
                "archive": str(archive),
                "files": len(manifest),
                "target_validation": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
