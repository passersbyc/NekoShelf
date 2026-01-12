import os
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional, Union
from PIL import Image
from core.utils import Colors
from tqdm import tqdm

def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    Sanitize filename by replacing illegal characters and removing control characters.
    """
    replacements = {
        '/': '／', '\\': '＼',
        ':': '：', '?': '？',
        '*': '＊', '"': '”',
        '<': '＜', '>': '＞',
        '|': '｜'
    }
    cleaned = name
    for char, repl in replacements.items():
        cleaned = cleaned.replace(char, repl)
        
    # Remove control characters
    cleaned = "".join(c for c in cleaned if c.isprintable())
    
    # Strip leading/trailing spaces and dots
    cleaned = cleaned.strip(". ")
    
    # Truncate if necessary (keeping extension is hard here as we don't know it, 
    # but usually this is used for the base name)
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
        
    return cleaned

def set_file_time(filepath: str, date_val: Union[str, float, datetime, None]):
    """
    Set the modification time of a file.
    :param date_val: Can be an ISO date string, a timestamp (float), or a datetime object.
    """
    if not date_val:
        return
        
    try:
        ts = 0.0
        if isinstance(date_val, (int, float)):
            ts = float(date_val)
        elif isinstance(date_val, datetime):
            ts = date_val.timestamp()
        elif isinstance(date_val, str):
            # Try parsing ISO format
            # Handle 'Z' which python < 3.11 might not handle gracefully with fromisoformat in some versions,
            # but usually fromisoformat handles +00:00
            dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
            ts = dt.timestamp()
            
        if ts > 0:
            os.utime(filepath, (ts, ts))
    except Exception:
        pass

def create_cbz(images: List[str], output_path: str, 
               title: str, author: str, 
               description: str = "", 
               source_url: str = "", 
               tags: List[str] = None, 
               series: str = "",
               published_time: Union[str, datetime, None] = None) -> bool:
    """
    Create a CBZ file from a list of images with ComicInfo.xml metadata.
    """
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_STORED) as zf:
            # Write images
            for i, img_path in enumerate(images):
                ext = os.path.splitext(img_path)[1]
                # Standardize image names to 001.ext, 002.ext for correct ordering in readers
                zf.write(img_path, f"{i+1:03d}{ext}")
            
            # Create ComicInfo.xml
            root = ET.Element("ComicInfo")
            ET.SubElement(root, "Title").text = title
            if series:
                ET.SubElement(root, "Series").text = series
            ET.SubElement(root, "Summary").text = description
            ET.SubElement(root, "Writer").text = author
            ET.SubElement(root, "PageCount").text = str(len(images))
            if source_url:
                ET.SubElement(root, "Web").text = source_url
            
            if tags:
                ET.SubElement(root, "Tags").text = ",".join(tags).replace(",", "，")
            
            if published_time:
                try:
                    dt = None
                    if isinstance(published_time, str):
                        dt = datetime.fromisoformat(published_time.replace("Z", "+00:00"))
                    elif isinstance(published_time, datetime):
                        dt = published_time
                        
                    if dt:
                        ET.SubElement(root, "Year").text = str(dt.year)
                        ET.SubElement(root, "Month").text = str(dt.month)
                        ET.SubElement(root, "Day").text = str(dt.day)
                except Exception:
                    pass
            
            if hasattr(ET, 'indent'):
                ET.indent(root, space="  ")
            zf.writestr("ComicInfo.xml", ET.tostring(root, encoding='utf-8', method='xml'))
            
        # Update timestamp
        set_file_time(output_path, published_time)
        tqdm.write(Colors.green(f"已生成 CBZ: {os.path.basename(output_path)}"))
        return True
    except Exception as e:
        tqdm.write(Colors.red(f"CBZ 打包失败: {e}"))
        return False

def create_pdf(images: List[str], output_path: str, 
               title: str, author: str, 
               tags: List[str] = None,
               published_time: Union[str, datetime, None] = None) -> bool:
    """
    Create a PDF file from a list of images.
    Requires Pillow (PIL).
    """
    if not Image:
        tqdm.write(Colors.red("PDF 生成失败: 未安装 PIL (Pillow) 库喵！请运行 `pip install Pillow`"))
        return False
        
    try:
        pil_images = []
        for img_path in images:
            try:
                img = Image.open(img_path)
                # Convert to RGB (e.g. for PNG with transparency or CMYK)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                pil_images.append(img)
            except Exception:
                pass
        
        if not pil_images:
            tqdm.write(Colors.red("PDF 生成失败: 没有有效的图片喵..."))
            return False
            
        keywords = ", ".join(tags) if tags else ""
        
        # Save PDF
        pil_images[0].save(
            output_path, "PDF", resolution=100.0, save_all=True, append_images=pil_images[1:],
            title=title, author=author, keywords=keywords
        )
        
        # Close images
        for img in pil_images:
            img.close()
            
        # Update timestamp
        set_file_time(output_path, published_time)
        tqdm.write(Colors.green(f"已生成 PDF: {os.path.basename(output_path)}"))
        return True
    except Exception as e:
        tqdm.write(Colors.red(f"PDF 生成失败: {e}"))
        return False
