import sys
import io

# 1. Заставляем терминал дружить с русским языком
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print("Парсер рецептов готов к работе!")
