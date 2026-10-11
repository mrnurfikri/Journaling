#!/usr/bin/env python3
"""Ambil dokumen jurnal dari Google Docs, urai per hari, enkripsi, tulis index.html.

Rahasia dibaca dari environment (GitHub Secrets):
  GOOGLE_SA_JSON    isi file JSON akun layanan Google
  JOURNAL_DOCS      "2025=<id dokumen>,2026=<id dokumen>"
  JOURNAL_PASSWORD  kata sandi halaman
Isi jurnal tidak pernah dicetak ke log.
"""
import argparse, base64, hashlib, hmac, json, os, re, sys
from pathlib import Path
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = Path(os.environ.get("OUT_DIR") or Path(__file__).resolve().parent.parent)
MIN_ENTRIES = int(os.environ.get("MIN_ENTRIES", "500"))  # pengaman: gagal jika hasil terlalu sedikit

MONTHS = {'januari':1,'january':1,'februari':2,'february':2,'maret':3,'march':3,'april':4,'may':5,'mei':5,
          'juni':6,'june':6,'juli':7,'july':7,'agustus':8,'august':8,'september':9,'sepember':9,
          'oktober':10,'october':10,'november':11,'desember':12,'december':12,'decmber':12}
MN = '|'.join(sorted(MONTHS, key=len, reverse=True))
A = re.compile(r'^\s*\**\s*(\d{1,2})\s*/\s*(\d{1,2})\s*\**\s*[:;.\-–]?\s*(.*)$')
B = re.compile(r'^\s*\**\s*(\d{1,2})\s+(' + MN + r')\b\**\s*$', re.I)


def fix_mojibake(c):
    if not re.search(r'[\u00c2-\u00f4][\u0080-\u00bf]', c):
        return c
    return re.sub(r'[\u00c2-\u00f4][\u0080-\u00bf]+',
                  lambda m: m.group(0).encode('latin-1', 'ignore').decode('utf-8', 'ignore'), c)


def clean(s):
    s = re.sub(r'\*\*|__', '', s)
    s = re.sub(r'\\([!&\.\-\(\)\*\_#\+\[\]>~`|=])', r'\1', s)
    return s.rstrip()


def parse(text, year):
    lines = fix_mojibake(text).split('\n')
    sec = None; month = None; out = []; cur = None

    def flush():
        nonlocal cur
        if cur:
            t = '\n'.join(cur['lines']); t = re.sub(r'\n{3,}', '\n\n', t).strip()
            t = re.sub(r'^[\s*]+$', '', t)
            if t:
                out.append(dict(y=year, s=cur['s'], m=cur['m'], d=cur['d'], t=t))
        cur = None

    for l in lines:
        if l.startswith('#'):
            flush()
            h = l.upper()
            if 'DAILY' in h: sec = 'harian'; month = None; continue
            if 'JOY' in h: sec = 'syukur'; month = None; continue
            if 'GROW' in h: sec = 'belajar'; month = None; continue
            if 'ENGLISH VERSION' in h: sec = 'english'; month = None; continue
            if 'NEW WORDS' in h: sec = 'english'; month = 0; continue
            w = re.search(r'[A-Za-z]+', l.replace('#', ''))
            month = MONTHS.get(w.group(0).lower()) if w else None
            if month is None and not l.strip('# *'): sec = None
            continue
        if sec is None or month is None: continue
        if month == 0:
            cur = cur or dict(s=sec, m=0, d=0, lines=[]); cur['lines'].append(clean(l)); continue
        ma = A.match(l); mb = B.match(l)
        if ma and int(ma.group(2)) == month and 1 <= int(ma.group(1)) <= 31:
            flush()
            first = clean(ma.group(3))
            cur = dict(s=sec, m=month, d=int(ma.group(1)), lines=[first] if first.strip('* ') else [])
        elif mb and 1 <= int(mb.group(1)) <= 31:
            flush(); cur = dict(s=sec, m=month, d=int(mb.group(1)), lines=[])
        else:
            if cur is None: cur = dict(s=sec, m=month, d=0, lines=[])
            cur['lines'].append(clean(l))
    flush()
    return [e for e in out if not (e['d'] == 0 and len(e['t']) < 5)]


def fetch_markdown(doc_id):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    info = json.loads(os.environ['GOOGLE_SA_JSON'])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=['https://www.googleapis.com/auth/drive.readonly'])
    r = AuthorizedSession(creds).get(
        f'https://www.googleapis.com/drive/v3/files/{doc_id}/export',
        params={'mimeType': 'text/markdown'}, timeout=120)
    if r.status_code != 200:
        try:
            e = r.json().get('error', {})
            reasons = ', '.join(x.get('reason', '') for x in e.get('errors', []))
            detail = f"{e.get('status', '')} | {reasons} | {str(e.get('message', ''))[:300]}"
        except Exception:
            detail = r.text[:200]
        sys.exit(f'Gagal mengambil dokumen (HTTP {r.status_code}). Alasan dari Google: {detail}\n'
                 f'Cek: Drive API aktif, dokumen dibagikan ke email akun layanan, dan ID dokumen benar.')
    r.encoding = 'utf-8'
    return r.text


def encrypt(payload: bytes, password: str) -> str:
    norm = re.sub(r'[^a-z0-9]', '', password.lower())
    if not norm:
        sys.exit('Kata sandi kosong atau hanya berisi simbol.')
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600000).derive(norm.encode())
    return base64.b64encode(salt + iv + AESGCM(key).encrypt(iv, payload, None)).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--local', nargs='*', help='uji lokal: 2025=berkas.md 2026=berkas.md')
    args = ap.parse_args()

    password = os.environ.get('JOURNAL_PASSWORD', '')
    if not password:
        sys.exit('JOURNAL_PASSWORD belum diisi.')

    sources = {}  # tahun -> (teks, id)
    if args.local:
        for item in args.local:
            y, p = item.split('=', 1)
            sources[int(y)] = (Path(p).read_text(encoding='utf-8'), None)
    else:
        docs = dict(x.split('=', 1) for x in os.environ.get('JOURNAL_DOCS', '').split(',') if '=' in x)
        if not docs:
            sys.exit('JOURNAL_DOCS belum diisi (format: 2025=ID,2026=ID).')
        for y, did in docs.items():
            sources[int(y.strip())] = (fetch_markdown(did.strip()), did.strip())

    entries, links = [], []
    for y in sorted(sources):
        text, did = sources[y]
        got = parse(text, y)
        print(f'{y}: {len(got)} entri')
        entries += got
        if did:
            links.append([f'Dokumen {y}', f'https://docs.google.com/document/d/{did}/edit'])
    if len(entries) < MIN_ENTRIES:
        sys.exit(f'Hanya {len(entries)} entri (minimal {MIN_ENTRIES}). Halaman lama tidak ditimpa. '
                 f'Cek format dokumen atau ekspor Google.')

    payload = json.dumps({'entries': entries, 'links': links}, ensure_ascii=False).encode()
    digest = hmac.new(password.encode(), payload, hashlib.sha256).hexdigest()
    hash_file, out_file = ROOT / '.last-hash', ROOT / 'index.html'
    if (hash_file.exists() and out_file.exists() and hash_file.read_text().strip() == digest
            and os.environ.get('FORCE', '').lower() != 'true'):
        print('Isi jurnal dan kata sandi tidak berubah; tidak perlu menulis ulang.')
        return
    html = (ROOT / 'template.html').read_text(encoding='utf-8').replace('__BLOB__', encrypt(payload, password))
    out_file.write_text(html, encoding='utf-8')
    hash_file.write_text(digest + '\n')
    print(f'index.html diperbarui ({len(entries)} entri).')


if __name__ == '__main__':
    main()
