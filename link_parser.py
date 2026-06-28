import aiohttp
from bs4 import BeautifulSoup
import sys
import io
import logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

async def get_text_via_bs4(url: str) -> str:
    # Асинхронно скачивает страницу кулинарного сайта 
    # и вычищает HTML-мусор, возвращая только чистый текст.
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    return f"Ошибка: Сервер вернул статус {response.status}"
                html_text = await response.text()
        
        soup = BeautifulSoup(html_text, 'html.parser')
        
        # 1. Удаляем весь мусор, в котором точно нет текста рецепта
        for trash in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
            trash.decompose()
            
        # 2. Извлекаем оставшийся текст
        text = soup.get_text(separator='\n')
        
        # 3. Чистим пустые строки и лишние пробелы
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return clean_text

    except Exception as e:
        logging.error(f"Ошибка парсинга сайта: {e}")
        return ""