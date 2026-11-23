import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta

SOURCE_URL = "https://tinyurl.com/xoilacz3"

SPORTS_KEYWORDS = [
    "xôi lạc", "xoilac", "gà vàng", "gavang", "chuối chiên", "chuoichien",
    "giờ vàng", "giovang", "khô gà", "khoga", "sao kê", "saoke",
    "sút bóng", "sutbong", "phá làng", "phalang", "xôi gấc", "xoigac",
    "thể thao", "bóng đá", "trực tiếp", "live", "cà khịa", "cakhiatv",
    "thập cẩm", "thapcam", "ném biên", "nembien", "khán đài", "khandai",
    "bia ôm", "biaom", "s8tv", "xôi chè", "xoiche", "bông lau", "bonglau",
    "sport", "football", "soccer"
]

TV_EXCEPTIONS = ["vtvcab", "sctv", "htv", "vtv", "k+", "on sports", "on football"]

def fetch_source(url):
    headers_list = [
        {
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; Kienplayer) AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36",
            "Accept": "*/*",
            "Referer": "https://tinyurl.com/",
        },
        {
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 14; Build/UP1A)",
            "Accept": "*/*",
        }
    ]
    last_err = None
    for idx, headers in enumerate(headers_list, 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                final_url = resp.geturl()
                body = resp.read().decode("utf-8", errors="ignore")
                print(f"[Header #{idx}] Final URL: {final_url} | Độ dài: {len(body)} ký tự")
                if body.strip():
                    return body
        except Exception as e:
            last_err = e
            print(f"[Header #{idx}] Lỗi tải: {e}")
    raise RuntimeError(f"Không tải được nguồn: {last_err}")

def is_sports_group(group_name, channel_name):
    g_low = (group_name or "").lower()
    c_low = (channel_name or "").lower()
    if any(exc in g_low for exc in TV_EXCEPTIONS):
        return False
    combined = f"{g_low} {c_low}"
    return any(kw in combined for kw in SPORTS_KEYWORDS)

def parse_m3u_text(content):
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    tv_entries = []
    sports_entries = []
    current_extinf = None
    extra_lines = []

    for line in lines:
        if line.startswith("#EXTM3U"):
            continue
        elif line.startswith("#EXTINF:"):
            current_extinf = line
            extra_lines = []
        elif line.startswith("#") and current_extinf:
            extra_lines.append(line)
        elif not line.startswith("#") and current_extinf:
            stream_url = line
            group_match = re.search(r'group-title="([^"]*)"', current_extinf, re.IGNORECASE)
            group_name = group_match.group(1).strip() if group_match else "Khác"
            channel_name = current_extinf.split(",")[-1].strip()

            if is_sports_group(group_name, channel_name):
                if group_name in ["", "Khác", "Undefined"]:
                    group_name = "Thể Thao Tổng Hợp"
                if group_match:
                    new_extinf = re.sub(r'group-title="[^"]*"', f'group-title="{group_name}"', current_extinf)
                else:
                    new_extinf = current_extinf.replace("#EXTINF:-1", f'#EXTINF:-1 group-title="{group_name}"', 1)
                sports_entries.append((group_name, new_extinf, extra_lines, stream_url))
            else:
                if group_name in ["", "Undefined"]:
                    group_name = "Truyền Hình Khác"
                    if group_match:
                        new_extinf = re.sub(r'group-title="[^"]*"', f'group-title="{group_name}"', current_extinf)
                    else:
                        new_extinf = current_extinf.replace("#EXTINF:-1", f'#EXTINF:-1 group-title="{group_name}"', 1)
                else:
                    new_extinf = current_extinf
                tv_entries.append((group_name, new_extinf, extra_lines, stream_url))

            current_extinf = None
            extra_lines = []

    return tv_entries, sports_entries

def parse_json_fallback(content):
    """Dự phòng nếu nguồn trả về JSON chứa danh sách kênh/trận"""
    tv_entries = []
    sports_entries = []
    try:
        data = json.loads(content)
    except Exception:
        return tv_entries, sports_entries

    def walk(obj, current_group=""):
        if isinstance(obj, dict):
            grp = obj.get("group") or obj.get("group_title") or obj.get("category") or obj.get("source_name") or current_group
            name = obj.get("name") or obj.get("title") or obj.get("label") or ""
            url = obj.get("url") or obj.get("stream") or obj.get("stream_url") or obj.get("m3u8") or obj.get("play_url") or ""
            if isinstance(url, str) and url.startswith("http"):
                g_clean = str(grp).strip() or "Khác"
                n_clean = str(name).strip() or "Kênh"
                extinf = f'#EXTINF:-1 group-title="{g_clean}",{n_clean}'
                if is_sports_group(g_clean, n_clean):
                    sports_entries.append((g_clean, extinf, [], url.strip()))
                else:
                    tv_entries.append((g_clean, extinf, [], url.strip()))
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v, grp)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, current_group)

    walk(data)
    return tv_entries, sports_entries

def write_m3u_file(filename, entries, tab_label):
    vn_tz = timezone(timedelta(hours=7))
    now_str = datetime.now(vn_tz).strftime("%H:%M %d/%m/%Y")

    with open(filename, "w", encoding="utf-8") as f:
        f.write('#EXTM3U url-tvg="https://epg.io.vn/epgc.xml"\n')
        f.write(f'#EXTINF:-1 group-title="🔄 Cập nhật: {now_str}",{tab_label} - Auto Update GitHub\n')
        f.write('http://localhost/update.m3u8\n')

        for _, extinf, extras, url in entries:
            f.write(f"{extinf}\n")
            for ex in extras:
                f.write(f"{ex}\n")
            f.write(f"{url}\n")

def main():
    print("Đang tải dữ liệu từ nguồn...")
    raw_content = fetch_source(SOURCE_URL)

    # In 300 ký tự đầu để kiểm tra định dạng thực tế
    preview = raw_content.strip()[:300].replace("\n", " | ")
    print(f"Xem trước nội dung: {preview}")

    tv_list, sports_list = parse_m3u_text(raw_content)

    # Nếu không có #EXTINF:, thử parse dạng JSON
    if not tv_list and not sports_list:
        tv_list, sports_list = parse_json_fallback(raw_content)

    write_m3u_file("truyen_hinh.m3u", tv_list, "TRUYỀN HÌNH")
    write_m3u_file("the_thao.m3u", sports_list, "THỂ THAO")

    combined_list = []
    for g, ext, ex, u in sports_list:
        new_ext = re.sub(r'group-title="([^"]*)"', r'group-title="⚽ THỂ THAO | \1"', ext)
        combined_list.append((g, new_ext, ex, u))
    for g, ext, ex, u in tv_list:
        new_ext = re.sub(r'group-title="([^"]*)"', r'group-title="📺 TRUYỀN HÌNH | \1"', ext)
        combined_list.append((g, new_ext, ex, u))

    write_m3u_file("tong_hop_xoilacz3.m3u", combined_list, "TỔNG HỢP")
    print(f"Hoàn tất! Đã tách {len(tv_list)} kênh Truyền hình và {len(sports_list)} kênh Thể thao.")

if __name__ == "__main__":
    main()
    
