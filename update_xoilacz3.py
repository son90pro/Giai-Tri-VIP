import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

SOURCE_URL = "https://tinyurl.com/xoilacz3"

def fetch_text(url, referer=None, timeout=10):
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

def prettify_title_from_url(url, fallback_idx):
    """Tự suy ra tên trận đấu từ đường dẫn .m3u8 nếu không có tiêu đề rõ ràng"""
    try:
        path = urllib.parse.urlparse(url).path
        parts = [p for p in path.split("/") if p and p.lower() not in ("live", "hls", "stream", "play", "index.m3u8", "playlist.m3u8")]
        # Bỏ các đoạn UUID/hash dài
        meaningful = []
        for p in parts:
            p_clean = re.sub(r"\.(m3u8|ts|mp4)$", "", p, flags=re.IGNORECASE)
            if len(p_clean) >= 3 and not re.fullmatch(r"[0-9a-fA-F-]{16,}", p_clean):
                meaningful.append(p_clean.replace("-", " ").replace("_", " ").strip())
        if meaningful:
            # Lấy phần tên trận rõ nhất (thường là đoạn chữ dài nhất)
            best = max(meaningful, key=len)
            best = re.sub(r"\s+", " ", best).title()
            if len(best) >= 3:
                return best
    except Exception:
        pass
    return f"Trận đấu #{fallback_idx}"

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

def extract_streams_from_content(raw):
    """Bóc các link phát (.m3u8 / luồng live) và tên trận từ JSON hoặc HTML/JS"""
    results = []
    seen_urls = set()

    def add_item(title, u):
        u_clean = (u or "").replace("\\/", "/").strip()
        if not u_clean.startswith("http") or u_clean in seen_urls:
            return
        # Bỏ qua file js/css/ảnh/json không phải luồng phát
        if re.search(r"\.(js|css|png|jpg|jpeg|gif|svg|ico|woff2?|json)(\?|$)", u_clean, re.IGNORECASE):
            return
        if ".m3u8" in u_clean.lower() or "/live/" in u_clean.lower() or "/hls/" in u_clean.lower():
            seen_urls.add(u_clean)
            t_clean = re.sub(r"\s+", " ", (title or "")).strip()
            if not t_clean or t_clean.lower() in ("stream", "live", "play", "link"):
                t_clean = prettify_title_from_url(u_clean, len(results) + 1)
            results.append((t_clean, u_clean))

    # 1. Thử parse JSON nếu là dữ liệu JSON
    try:
        data = json.loads(raw)
        def walk_json(obj, hint=""):
            if isinstance(obj, dict):
                home = obj.get("home_name") or obj.get("home") or ""
                away = obj.get("away_name") or obj.get("away") or ""
                league = obj.get("league_name") or obj.get("league") or ""
                vs_title = f"{home} vs {away}".strip(" vs") if (home or away) else ""
                cur_title = obj.get("title") or obj.get("name") or obj.get("match_name") or vs_title or hint
                if cur_title and league and str(league).lower() not in str(cur_title).lower():
                    cur_title = f"[{league}] {cur_title}"

                for k, v in obj.items():
                    if isinstance(v, str) and v.startswith("http"):
                        if any(x in v.lower() for x in [".m3u8", "/live/", "/hls/"]) or any(x in k.lower() for x in ["m3u8", "stream", "play_url", "live_url"]):
                            add_item(str(cur_title), v)
                    elif isinstance(v, (dict, list)):
                        walk_json(v, str(cur_title))
            elif isinstance(obj, list):
                for item in obj:
                    walk_json(item, hint)
        walk_json(data)
    except Exception:
        pass

    # 2. Quét link .m3u8 / luồng trực tiếp trong HTML / JS / text
    url_pattern = r'https?://[^\s"\'<>\\]+\.(?:m3u8)[^\s"\'<>\\]*'
    for m in re.finditer(url_pattern, raw, re.IGNORECASE):
        u_raw = m.group(0)
        start = max(0, m.start() - 300)
        snippet = raw[start:m.start()]

        # Tìm tiêu đề gần nhất trong đoạn trước URL
        title_candidates = re.findall(
            r'(?:["\'](?:title|name|match|label|team)["\']\s*[:=]\s*["\']|data-title=["\']|>)\s*([^"\'<>]{3,90})',
            snippet,
            re.IGNORECASE
        )
        title_found = ""
        for cand in reversed(title_candidates):
            c = cand.strip()
            if c and not c.startswith("http") and "{" not in c and "}" not in c:
                title_found = c
                break

        add_item(title_found, u_raw)

    return results

def fetch_sports_matches(providers):
    sports_items = []

    for prov in providers:
        if not isinstance(prov, dict):
            continue
        p_id = str(prov.get("id", "")).lower()
        p_name = clean_group_name(prov.get("name", ""))
        p_url = (prov.get("url") or "").strip()

        if p_id == "m3u-playlist" or p_name.lower() in ["truyền hình", "truyen hinh", "tv"]:
            continue
        if not p_url.startswith("http"):
            continue

        parsed = urllib.parse.urlparse(p_url)
        root_domain = f"{parsed.scheme}://{parsed.netloc}"

        try:
            body = fetch_text(p_url, referer=root_domain + "/", timeout=10)
            if "#EXTINF:" in body:
                parsed_m3u = parse_tv_m3u(body)
                for _, ext, exs, s_url in parsed_m3u:
                    ch_title = ext.rsplit(",", 1)[-1].strip()
                    sports_items.append((p_name, f'#EXTINF:-1 group-title="{p_name}",{ch_title}', exs, s_url))
            else:
                streams = extract_streams_from_content(body)
                for st_title, st_url in streams:
                    sports_items.append((p_name, f'#EXTINF:-1 group-title="{p_name}",{st_title}', [], st_url))
        except Exception as e:
            print(f"[Thể thao - {p_name}] {p_url} -> {e}")

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
    raw_json = fetch_text(SOURCE_URL, timeout=15)
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
                m3u_body = fetch_text(tv_url, timeout=15)
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
    
