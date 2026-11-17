import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path.cwd()
STAGING = ROOT / "kaggle_dataset_staging" / "quarto-two-model-source-v1"

WORKSPACE_TO_STAGED = {
    "quarto_two_model_match.py": ROOT / "kaggle_task" / "quarto_two_model_match.py",
    "kaggle_agent_adapter.py": ROOT / "kaggle_agent_adapter.py",
    "tournament_harness.py": ROOT / "tournament_harness.py",
    "phase0_foundation.py": ROOT / "phase0_foundation.py",
    "quarto_engine.py": ROOT / "quarto_engine.py",
    "decision_trace.py": ROOT / "decision_trace.py",
    "fma_pilot.py": ROOT / "fma_pilot.py",
    "fma_pilot_instance.json": ROOT / "fma_pilot_instance.json",
    "ATTRIBUTION.md": ROOT / "ATTRIBUTION.md",
    "requirements.txt": ROOT / "requirements.txt",
}

EVALUATOR_MEMBERS = [
    "evaluator/__init__.py",
    "evaluator/__main__.py",
    "evaluator/adapters.py",
    "evaluator/annotations.py",
    "evaluator/automated.py",
    "evaluator/metrics.py",
    "evaluator/report.py",
    "evaluator/semantic_judge.py",
]

DOMAIN_ADAPTER_MEMBERS = [
    "domain_adapters/__init__.py",
    "domain_adapters/instance_builder.py",
    "domain_adapters/dataset_adapter.py",
    "domain_adapters/fma_adapter.py",
    "domain_adapters/qm9_adapter.py",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)

    # 1. کپی فایل‌های اصلی از workspace به staging (اگر فایلی مثل ATTRIBUTION.md فقط در staging بود حفظ می‌شود)
    for staged_name, src_path in WORKSPACE_TO_STAGED.items():
        dst_path = STAGING / staged_name
        if src_path.is_file():
            shutil.copyfile(src_path, dst_path)
        elif not dst_path.is_file():
            raise FileNotFoundError(f"Missing required source file: {src_path}")

    # 2. ساخت قطعی (deterministic) آرشیو domain_adapters.zip و ثبت متادیتای اعضا
    archive_path = STAGING / "domain_adapters.zip"
    archive_members_meta = []
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_posix in DOMAIN_ADAPTER_MEMBERS:
            src_member = ROOT / Path(rel_posix)
            if not src_member.is_file():
                raise FileNotFoundError(f"Missing domain adapter member: {src_member}")
            data = src_member.read_bytes()
            info = zipfile.ZipInfo(filename=rel_posix, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
            archive_members_meta.append({
                "path": rel_posix,
                "size_bytes": len(data),
                "sha256": sha256_bytes(data),
            })

    # 3. محاسبه هش و حجم ۱۱ فایل موجود در اسنپ‌شات
    eval_archive_path = STAGING / "evaluator.zip"
    eval_members_meta = []
    with zipfile.ZipFile(eval_archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_posix in EVALUATOR_MEMBERS:
            src_member = ROOT / Path(rel_posix)
            if not src_member.is_file():
                raise FileNotFoundError(f"Missing evaluator member: {src_member}")
            data = src_member.read_bytes()
            info = zipfile.ZipInfo(filename=rel_posix, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
            eval_members_meta.append({
                "path": rel_posix,
                "size_bytes": len(data),
                "sha256": sha256_bytes(data),
            })

    all_staged_names = sorted(list(WORKSPACE_TO_STAGED.keys()) + ["domain_adapters.zip", "evaluator.zip"])
    included_files_meta = []
    for name in all_staged_names:
        file_bytes = (STAGING / name).read_bytes()
        included_files_meta.append({
            "path": name,
            "size_bytes": len(file_bytes),
            "sha256": sha256_bytes(file_bytes),
        })

    # 4. به‌روزرسانی manifest.json و manifest.sha256
    manifest_path = STAGING / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    manifest["snapshot_id"] = "quarto-two-model-source-v1"
    manifest["included_files"] = included_files_meta
    manifest["archive_members"] = archive_members_meta
    manifest["evaluator_members"] = eval_members_meta

    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)

    manifest_digest = sha256_bytes(manifest_bytes)
    (STAGING / "manifest.sha256").write_text(
        f"{manifest_digest}  manifest.json\n",
        encoding="utf-8",
    )

    print(f"Staging synced successfully. manifest.json sha256 = {manifest_digest}")


if __name__ == "__main__":
    main()