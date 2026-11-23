import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

SOURCE_URL = "https://tinyurl.com/xoilacz3"

def fetch_text(url, referer=None, extra_headers=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
        "Accept": "*/*",
    }
    if referer:
        headers["Referer"] = referer
        headers["Origin"] = referer.rstrip("/")
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def clean_group_name(grp):
    g = re.sub(r"\s+", " ", (grp or "").strip())
    return g if g else "Khác"

def parse_tv_m3u(m3u_text):
    """Parse chuẩn file M3U truyền hình gốc, giữ nguyên nhóm VTV, VTVcab, HTV..."""
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
            # Bỏ qua các dòng thông báo/link giả nếu có
            if not url.startswith("http") or "localhost" in url:
                extinf = None
                extras = []
                continue

            m_grp = re.search(r'group-title="([^"]*)"', extinf, re.IGNORECASE)
            grp = clean_group_name(m_grp.group(1) if m_grp else "Truyền Hình")

            # Chuẩn hóa tên kênh sau dấu phẩy cuối
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

def extract_streams_from_html_or_json(raw, base_url):
    """Tìm các link .m3u8 / luồng phát kèm tiêu đề nếu trang/API trả về dữ liệu"""
    matches = []

    # 1. Thử parse JSON nếu có danh sách trận/kênh
    try:
        data = json.loads(raw)
        def walk_json(obj, title_hint=""):
            if isinstance(obj, dict):
                t = (
                    obj.get("title") or obj.get("name") or obj.get("match_name")
                    or obj.get("home") and obj.get("away") and f"{obj.get('home')} vs {obj.get('away')}"
                    or title_hint
                )
                for k, v in obj.items():
                    if isinstance(v, str) and v.startswith("http") and (".m3u8" in v or "live" in v or "stream" in v or "play" in k.lower()):
                        matches.append((str(t).strip() or "Trận đấu trực tiếp", v.strip()))
                    elif isinstance(v, (dict, list)):
                        walk_json(v, str(t))
            elif isinstance(obj, list):
                for item in obj:
                    walk_json(item, title_hint)
        walk_json(data)
        if matches:
            return matches
    except Exception:
        pass

    # 2. Tìm trực tiếp các URL .m3u8 trong HTML/JS/text
    m3u8_urls = re.findall(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', raw, re.IGNORECASE)
    seen = set()
    for idx, u in enumerate(m3u8_urls, 1):
        u_clean = u.replace("\\/", "/")
        if u_clean not in seen:
            seen.add(u_clean)
            # Cố gắng tìm tiêu đề gần vị trí link
            pos = raw.find(u)
            snippet = raw[max(0, pos - 250):pos]
            title_m = re.findall(r'["\'](?:title|name|match|label)["\']\s*[:=]\s*["\']([^"\']{3,80})["\']', snippet, re.IGNORECASE)
            title = title_m[-1].strip() if title_m else f"Luồng phát #{idx}"
            matches.append((title, u_clean))

    return matches

def fetch_sports_matches(providers):
    """Chỉ lấy các trận đấu thực sự có link phát từ các nguồn thể thao"""
    sports_items = []

    for prov in providers:
        if not isinstance(prov, dict):
            continue
        p_id = str(prov.get("id", "")).lower()
        p_name = clean_group_name(prov.get("name", ""))
        p_url = (prov.get("url") or "").strip()

        # Bỏ qua provider truyền hình M3U chính
        if p_id == "m3u-playlist" or p_name.lower() in ["truyền hình", "truyen hinh", "tv"]:
            continue
        if not p_url.startswith("http"):
            continue

        # Thử lấy dữ liệu từ URL nguồn thể thao (và thử thêm /cms-schedule.json nếu có)
        candidate_urls = [p_url]
        parsed = urllib.parse.urlparse(p_url)
        root_domain = f"{parsed.scheme}://{parsed.netloc}"
        if parsed.path in ["", "/"]:
            candidate_urls.append(f"{root_domain}/cms-schedule.json")

        found_for_provider = []
        for c_url in candidate_urls:
            try:
                body = fetch_text(c_url, referer=root_domain + "/")
                if "#EXTINF:" in body:
                    parsed_m3u = parse_tv_m3u(body)
                    for _, ext, exs, s_url in parsed_m3u:
                        ch_title = ext.rsplit(",", 1)[-1].strip()
                        found_for_provider.append((ch_title, s_url, exs))
                else:
                    streams = extract_streams_from_html_or_json(body, c_url)
                    for st_title, st_url in streams:
                        found_for_provider.append((st_title, st_url, []))
                if found_for_provider:
                    break
            except Exception as e:
                print(f"[Thể thao - {p_name}] Bỏ qua {c_url}: {e}")

        for match_title, stream_url, exs in found_for_provider:
            extinf = f'#EXTINF:-1 group-title="{p_name}",{match_title}'
            sports_items.append((p_name, extinf, exs, stream_url))

    return sports_items

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
    raw_json = fetch_text(SOURCE_URL)
    data = json.loads(raw_json)
    providers = data.get("providers", [])

    # 1. Lấy danh sách Truyền hình chuẩn từ provider m3u-playlist
    tv_items = []
    for prov in providers:
        if isinstance(prov, dict) and (
            str(prov.get("id", "")).lower() == "m3u-playlist"
            or clean_group_name(prov.get("name", "")).lower() in ["truyền hình", "truyen hinh"]
        ):
            tv_url = (prov.get("url") or "").strip()
            if tv_url.startswith("http"):
                print(f"Đang tải M3U Truyền hình: {tv_url}")
                m3u_body = fetch_text(tv_url)
                tv_items = parse_tv_m3u(m3u_body)
                break

    # 2. Lấy danh sách trận đấu Thể thao có link phát thật
    print("Đang quét các nguồn thể thao...")
    sports_items = fetch_sports_matches(providers)

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
    
