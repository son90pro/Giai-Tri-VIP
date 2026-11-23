import re
import urllib.request
from datetime import datetime, timezone, timedelta

SOURCE_URL = "https://tinyurl.com/xoilacz3"

# Từ khóa nhận diện các nhóm thuộc tab Thể Thao (không phân biệt hoa thường)
SPORTS_KEYWORDS = [
    "xôi lạc", "xoilac", "gà vàng", "gavang", "chuối chiên", "chuoichien",
    "giờ vàng", "giovang", "khô gà", "khoga", "sao kê", "saoke",
    "sút bóng", "sutbong", "phá làng", "phalang", "xôi gấc", "xoigac",
    "thể thao", "bóng đá", "trực tiếp", "live", "cà khịa", "cakhiatv",
    "thập cẩm", "thapcam", "ném biên", "nembien", "khán đài", "khandai",
    "bia ôm", "biaom", "s8tv", "xôi chè", "xoiche", "bông lau", "bonglau"
]

def fetch_m3u(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*"
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def is_sports_group(group_name, channel_name):
    text_check = f"{group_name} {channel_name}".lower()
    # Loại trừ các kênh truyền hình thể thao cố định nếu muốn nằm bên tab Truyền Hình (VD: ON Sports, VTVcab Thể thao)
    tv_exceptions = ["vtvcab", "sctv", "htv", "vtv", "k+", "on sports", "on football"]
    if any(exc in group_name.lower() for exc in tv_exceptions):
        return False
    return any(kw in text_check for kw in SPORTS_KEYWORDS)

def parse_and_split_m3u(content):
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    
    tv_entries = []
    sports_entries = []
    
    current_extinf = None
    extra_lines = [] # Lưu các dòng như #EXTVLCOPT hoặc #KODIPROP nếu có

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
            
            # Lấy group-title hiện tại
            group_match = re.search(r'group-title="([^"]*)"', current_extinf, re.IGNORECASE)
            group_name = group_match.group(1).strip() if group_match else "Khác"
            
            # Lấy tên kênh sau dấu phẩy cuối cùng
            channel_name = current_extinf.split(",")[-1].strip()
            
            # Kiểm tra thuộc Thể Thao hay Truyền Hình
            if is_sports_group(group_name, channel_name):
                # Chuẩn hóa tên nhóm Thể thao nếu nguồn chưa gắn group-title chuẩn
                if group_name in ["", "Khác", "Undefined"]:
                    group_name = "Thể Thao Tổng Hợp"
                
                # Cập nhật lại group-title trong #EXTINF
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

def write_m3u_file(filename, entries, tab_label):
    vn_tz = timezone(timedelta(hours=7))
    now_str = datetime.now(vn_tz).strftime("%H:%M %d/%m/%Y")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write('#EXTM3U url-tvg="https://epg.io.vn/epgc.xml"\n')
        # Tạo 1 mục thông báo thời gian cập nhật ở đầu danh sách
        f.write(f'#EXTINF:-1 group-title="🔄 Cập nhật: {now_str}",{tab_label} - Auto Update GitHub\n')
        f.write('http://localhost/update.m3u8\n')
        
        for group_name, extinf, extras, url in entries:
            f.write(f"{extinf}\n")
            for ex in extras:
                f.write(f"{ex}\n")
            f.write(f"{url}\n")

def main():
    print("Đang tải dữ liệu từ nguồn...")
    raw_content = fetch_m3u(SOURCE_URL)
    tv_list, sports_list = parse_and_split_m3u(raw_content)
    
    write_m3u_file("truyen_hinh.m3u", tv_list, "TRUYỀN HÌNH")
    write_m3u_file("the_thao.m3u", sports_list, "THỂ THAO")
    
    # Tạo thêm 1 file gộp chung có phân tiền tố [TV] và [Thể Thao] nếu anh muốn dùng 1 link duy nhất
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
