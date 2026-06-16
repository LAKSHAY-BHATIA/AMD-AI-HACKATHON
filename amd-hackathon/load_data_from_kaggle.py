from pathlib import Path
import shutil
import kagglehub

# Project root
PROJECT_ROOT = Path.cwd()

# Data directory
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Download dataset
cache_path = Path(
    kagglehub.dataset_download(
        "zoya77/industrial-robot-sensor-and-vision-fusion-dataset"
    )
)

print("Downloaded to:", cache_path)

# Copy dataset contents
for item in cache_path.iterdir():
    target = DATA_DIR / item.name

    if item.is_dir():
        shutil.copytree(item, target, dirs_exist_ok=True)
    else:
        shutil.copy2(item, target)

print("Dataset available at:", DATA_DIR.resolve())