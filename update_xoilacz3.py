import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

SOURCE_URL = "https://pub-5ead3f4154b54b7d8fb7e59d5ce390d1.r2.dev/xoilac.json"


def fetch_text(url, referer=None, timeout=15):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def clean_group_name(grp):
    g = re.sub(r"\s+", " ", (grp or "").strip())
    return g if g else "Khác"


def parse_tv_m3u(m3u_text):
    lines = [ln.strip() for ln in m3u_text.splitlines() if ln.strip()]
    tv_items = []
    extinf = None
    extras = []

    for ln in lines:
        if ln.startswith("#EXTM3U"):
            continue
        elif ln.startswith("#EXTINF:"):
            extinf = ln
            extras = []
        elif ln.startswith("#") and extinf:
            extras.append(ln)
        elif not ln.startswith("#") and extinf:
            url = ln
            if not url.startswith("http") or "localhost" in url:
                extinf = None
                extras = []
                continue

            m_grp = re.search(r'group-title="([^"]*)"', extinf, re.IGNORECASE)
            grp = clean_group_name(m_grp.group(1) if m_grp else "Truyền Hình")

            parts = extinf.rsplit(",", 1)
            ch_name = parts[1].strip() if len(parts) == 2 else "Kênh TV"
            header_part = parts[0]

            if m_grp:
                header_part = re.sub(r'group-title="[^"]*"', f'group-title="{grp}"', header_part)
            else:
                header_part = header_part + f' group-title="{grp}"'

            new_extinf = f"{header_part},{ch_name}"
            tv_items.append((grp, new_extinf, extras, url))
            extinf = None
            extras = []

    return tv_items


def write_m3u(filename, items, tab_label):
    vn_tz = timezone(timedelta(hours=7))
    now_str = datetime.now(vn_tz).strftime("%H:%M %d/%m/%Y")

    with open(filename, "w", encoding="utf-8") as f:
        f.write('#EXTM3U url-tvg="https://epg.io.vn/epgc.xml"\n')
        f.write(f'#EXTINF:-1 group-title="🔄 Cập nhật: {now_str}",{tab_label} - Auto Update GitHub\n')
        f.write("http://localhost/update.m3u8\n")

        for _, extinf, exs, url in items:
            f.write(f"{extinf}\n")
            for ex in exs:
                f.write(f"{ex}\n")
            f.write(f"{url}\n")


def main():
    print("Đang tải JSON nguồn...")
    raw_json = fetch_text(SOURCE_URL, timeout=20)
    data = json.loads(raw_json)

    # In cấu trúc chi tiết của xoilac.json để kiểm tra
    print("Top-level keys:", list(data.keys()))
    providers = data.get("providers", [])
    print(f"Tổng số providers: {len(providers)}")
    for idx, prov in enumerate(providers):
        if isinstance(prov, dict):
            print(
                f"Provider #{idx}: keys={list(prov.keys())} | "
                f"id={prov.get('id')} | name={prov.get('name')} | url={prov.get('url')}"
            )

    # Lấy danh sách Truyền hình từ provider M3U
    tv_items = []
    sports_items = []

    for prov in providers:
        if not isinstance(prov, dict):
            continue
        p_id = str(prov.get("id", "")).lower()
        p_name = clean_group_name(prov.get("name", ""))
        p_url = (prov.get("url") or "").strip()

        if p_id == "m3u-playlist" or p_name.lower() in ["truyền hình", "truyen hinh"]:
            if p_url.startswith("http"):
                print(f"Đang tải M3U Truyền hình: {p_url}")
                m3u_body = fetch_text(p_url, timeout=20)
                tv_items = parse_tv_m3u(m3u_body)
        else:
            # Nếu provider có sẵn danh sách trận/kênh dạng JSON hoặc M3U bên trong
            for key in ("matches", "streams", "channels", "items", "data"):
                sub = prov.get(key)
                if isinstance(sub, list):
                    for item in sub:
                        if isinstance(item, dict):
                            title = item.get("title") or item.get("name") or "Trận đấu"
                            s_url = item.get("url") or item.get("stream") or item.get("m3u8") or ""
                            if isinstance(s_url, str) and s_url.startswith("http"):
                                sports_items.append((p_name, f'#EXTINF:-1 group-title="{p_name}",{title}', [], s_url))

    write_m3u("truyen_hinh.m3u", tv_items, "TRUYỀN HÌNH")
    write_m3u("the_thao.m3u", sports_items, "THỂ THAO")

    combined = []
    for grp, ext, exs, u in sports_items:
        new_ext = re.sub(r'group-title="([^"]*)"', r'group-title="⚽ THỂ THAO | \1"', ext)
        combined.append((grp, new_ext, exs, u))
    for grp, ext, exs, u in tv_items:
        new_ext = re.sub(r'group-title="([^"]*)"', r'group-title="📺 TRUYỀN HÌNH | \1"', ext)
        combined.append((grp, new_ext, exs, u))

    write_m3u("tong_hop_xoilacz3.m3u", combined, "TỔNG HỢP")
    print(f"Xong! Truyền hình: {len(tv_items)} kênh | Thể thao: {len(sports_items)} trận/luồng.")


if __name__ == "__main__":
    main()
    
