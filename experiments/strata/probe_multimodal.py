#!/usr/bin/env python3
"""Probe image input; fixture creation uses Hermes' Pillow, requests use stdlib."""
import argparse
import base64
import io
import json
import os
import re
import time
import urllib.request
from pathlib import Path

def fixture():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new('RGB', (768, 512), 'white')
    draw = ImageDraw.Draw(image)
    draw.ellipse((50, 40, 220, 210), fill='red')
    draw.rectangle((50, 260, 290, 370), fill='blue')
    draw.polygon([(510, 50), (380, 350), (660, 350)], fill='green')
    draw.text((270, 410), '4827', fill='black', font=ImageFont.load_default(size=64))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('url', 'model', 'output'):
        p.add_argument('--' + key, required=True)
    p.add_argument('--key-env')
    p.add_argument('--image', help='Reuse a PNG fixture without requiring Pillow')
    a = p.parse_args()
    png = Path(a.image).read_bytes() if a.image else fixture()
    data_url = 'data:image/png;base64,' + base64.b64encode(png).decode()
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.png').write_bytes(png)
    headers = {'Content-Type': 'application/json'}
    if a.key_env:
        headers['Authorization'] = 'Bearer ' + os.environ[a.key_env]
    cases = (
        ('shapes', 'Beschreibe die drei farbigen Formen im Bild: jeweils Form, Farbe und Position. Keine Tools verwenden.'),
        ('ocr', 'Welche vierstellige Zahl steht unten im Bild? Antworte nur mit der Zahl. Keine Tools verwenden.'),
    )
    results = []
    for name, prompt in cases:
        payload = dict(model=a.model, messages=[
            {'role': 'system', 'content': 'Dies ist ein Bildtest. Antworte knapp auf Deutsch. Keine Tools oder Aktionen.'},
            {'role': 'user', 'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': data_url}},
            ]}], max_tokens=160, temperature=0, reasoning_effort='none', stream=False)
        req = urllib.request.Request(a.url.rstrip('/') + '/v1/chat/completions',
                                     data=json.dumps(payload).encode(), headers=headers)
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=300) as response:
            reply = json.load(response)
        choice = reply['choices'][0]
        text = (choice['message'].get('content') or '').lower()
        passed = (choice['finish_reason'] == 'stop' and not reply.get('hermes', {}).get('failed')
                  and (re.findall(r'\d+', text) == ['4827'] if name == 'ocr' else
                       all(word in text for word in ('kreis', 'rot', 'rechteck', 'blau', 'dreieck', 'grün'))))
        result = dict(case=name, model=a.model, url=a.url, passed=passed,
                      elapsed_s=time.monotonic()-start, reply=reply)
        results.append(result)
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    if not all(r['passed'] for r in results):
        raise SystemExit('Image probe failed; inspect the checkpointed responses.')


if __name__ == '__main__':
    main()
