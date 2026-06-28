import os
import sys
import io

# 1. Заставляем терминал дружить с русским языком
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 2. Настройка путей (чтобы избежать проблем с кириллицей в путях Windows)
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

os.environ["EASYOCR_MODULE_PATH"] = os.path.join(script_dir, "models")
os.environ["MODULE_PATH"] = os.path.join(script_dir, "models")

import easyocr

# 3. Создаем чистую папку для моделей
models_dir = os.path.join(script_dir, "models")
os.makedirs(models_dir, exist_ok=True)

print("⏳ Инициализация EasyOCR (загрузка моделей в память)...")
# Создаем ридер ОДИН раз при запуске бота
reader = easyocr.Reader(['ru', 'en'], model_storage_directory=models_dir)
print("✅ EasyOCR готов к работе!")

def extract_text_from_image(image_path: str) -> str:
    # Синхронная функция для извлечения текста из файла картинки.
    
    try:
        if not os.path.exists(image_path):
            return ""
        
        result = reader.readtext(image_path, detail=0)
        raw_text = " ".join(result)
        return raw_text.strip()
    except Exception as e:
        print(f"Ошибка EasyOCR: {e}")
        return ""