# cái này là để check mã ATC của thuốc theo tên hoạt chất, tra cứu từ Wikidata P267.
import pandas as pd
import requests
import re
import csv
import json
from datetime import datetime
from pathlib import Path

WIKIDATA_SEARCH_ENDPOINT = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITY_ENDPOINT = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
DAV_SEARCH_ENDPOINT = "https://dichvucong.dav.gov.vn/api/services/app/soDangKy/GetAllPublicServerPaging"
FILE_KET_QUA = "ma_atc_tu_dav.csv"
CACHE_FILE = "wikidata_atc_cache.json"
TEN_THUOC_TIENG_ANH = {
    "amoxicilin": "amoxicillin",
    "bupivacain hydroclorid": "bupivacaine",
    "halothan": "halothane",
    "ketamin": "ketamine",
}

def tra_cuu_thuoc(ten_hoat_chat, file_path="Danh_muc_thuoc_thiet_yeu.csv"):
    # Đọc file CSV, ép kiểu chuỗi để dễ tìm kiếm
    # Dùng engine python hoặc on_bad_lines='skip' để xử lý file có số cột không đều
    try:
        df = pd.read_csv(file_path, dtype=str, on_bad_lines='skip')
    except Exception as e:
        print(f"Lỗi đọc file: {e}")
        return

    # Quét từ khóa (không phân biệt hoa/thường) trên tất cả các cột
    mask = df.apply(lambda row: row.astype(str).str.contains(ten_hoat_chat, case=False, na=False).any(), axis=1)
    ket_qua = df[mask]
    
    if ket_qua.empty:
        print(f"Không tìm thấy thông tin cho: {ten_hoat_chat}")
    else:
        print(f"\n--- KẾT QUẢ TRA CỨU: {ten_hoat_chat.upper()} ---")
        # Xóa các cột trống hoàn toàn (do ghép nhiều bảng) để kết quả gọn nhất
        ket_qua = ket_qua.dropna(axis=1, how='all')
        print(ket_qua.to_string(index=False))

    # New functionality starts here

def chuan_hoa_ten(ten_hoat_chat):
    ten_sach = re.sub(r"\([^)]*\)", "", ten_hoat_chat).strip().casefold()
    return TEN_THUOC_TIENG_ANH.get(ten_sach, ten_sach)


def doc_cache_atc():
    try:
        with Path(CACHE_FILE).open(encoding="utf-8") as cache_file:
            return json.load(cache_file)
    except (OSError, json.JSONDecodeError):
        return {}


def luu_cache_atc(ten_chuan, ket_qua):
    cache = doc_cache_atc()
    cache[ten_chuan] = [
        {"ten": ten_thuoc, "ma": ma_atc} for ten_thuoc, ma_atc in ket_qua
    ]
    with Path(CACHE_FILE).open("w", encoding="utf-8") as cache_file:
        json.dump(cache, cache_file, ensure_ascii=False, indent=2)

def tra_cuu_ma_atc(ten_hoat_chat):
    ten_chuan = chuan_hoa_ten(ten_hoat_chat)
    headers = {
        "User-Agent": "PharmacyATCExample/1.0 (educational use)",
    }
    search_response = requests.get(
        WIKIDATA_SEARCH_ENDPOINT,
        params={
            "action": "wbsearchentities",
            "search": ten_chuan,
            "language": "en",
            "format": "json",
            "type": "item",
            "limit": 10,
        },
        headers=headers,
        timeout=15,
    )
    search_response.raise_for_status()

    entities = search_response.json().get("search", [])
    exact_matches = [
        item
        for item in entities
        if item.get("match", {}).get("text", "").casefold() == ten_chuan
    ]

    ket_qua = set()
    for item in exact_matches:
        entity_response = requests.get(
            WIKIDATA_ENTITY_ENDPOINT.format(item["id"]),
            headers=headers,
            timeout=15,
        )
        entity_response.raise_for_status()
        entity = entity_response.json().get("entities", {}).get(item["id"], {})
        ten_thuoc = entity.get("labels", {}).get("en", {}).get("value", item["label"])

        for claim in entity.get("claims", {}).get("P267", []):
            ma_atc = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if ma_atc:
                ket_qua.add((ten_thuoc, ma_atc))

    ket_qua = sorted(ket_qua, key=lambda item: item[1])
    if ket_qua:
        luu_cache_atc(ten_chuan, ket_qua)
    return ten_chuan, ket_qua


def tra_cuu_dav(ten_thuoc):
    payload = {
        "filterText": ten_thuoc,
        "SoDangKyThuoc": {},
        "KichHoat": True,
        "skipCount": 0,
        "maxResultCount": 10,
        "sorting": None,
    }
    response = requests.post(
        DAV_SEARCH_ENDPOINT,
        json=payload,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://dichvucong.dav.gov.vn/congbothuoc/index",
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise ValueError("Cổng DAV không trả về kết quả thành công.")

    result = data.get("result") or {}
    return result.get("totalCount", 0), result.get("items", [])


def thong_tin_hoat_chat(ho_so):
    thong_tin_co_ban = ho_so.get("thongTinThuocCoBan") or {}
    return (
        thong_tin_co_ban.get("hoatChatChinh")
        or ho_so.get("hoatChatChinh")
        or ho_so.get("tenHoatChatChinh")
        or ho_so.get("hoatChatDangKy")
        or ""
    )


def luu_ma_da_chon(ten_thuoc_dav, so_dang_ky, hoat_chat_dav, ten_chuan, ten_wikidata, ma_atc):
    file_path = Path(FILE_KET_QUA)
    can_tao_header = not file_path.exists() or file_path.stat().st_size == 0

    with file_path.open("a", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.writer(output_file)
        if can_tao_header:
            writer.writerow(
                [
                    "Tên thuốc DAV",
                    "Số đăng ký DAV",
                    "Hoạt chất DAV",
                    "Tên chuẩn Wikidata",
                    "Tên trên Wikidata",
                    "Mã ATC",
                    "Nguồn",
                    "Ngày xác nhận",
                ]
            )
        writer.writerow(
            [
                ten_thuoc_dav,
                so_dang_ky,
                hoat_chat_dav,
                ten_chuan,
                ten_wikidata,
                ma_atc,
                "DAV + Wikidata P267 (CC0)",
                datetime.now().date().isoformat(),
            ]
        )


def main():
    print("Tra tên thuốc trên cổng DAV, lấy hoạt chất rồi tra mã ATC.")
    print("Nhập tên thương mại; gõ q để thoát. Ví dụ: Venclexta.")

    while True:
        ten_nhap = input("\nTên thuốc: ").strip()
        if ten_nhap.casefold() == "q":
            break
        if not ten_nhap:
            continue

        try:
            tong_so, ho_so_thuoc = tra_cuu_dav(ten_nhap)
        except requests.RequestException as error:
            print(f"Không kết nối được cổng DAV: {error}")
            continue

        if not ho_so_thuoc:
            print(f"DAV không tìm thấy hồ sơ cho: {ten_nhap}")
            continue

        print(f"DAV tìm thấy {tong_so} hồ sơ; đang hiển thị {len(ho_so_thuoc)} hồ sơ đầu:")
        for index, ho_so in enumerate(ho_so_thuoc, start=1):
            thong_tin_co_ban = ho_so.get("thongTinThuocCoBan") or {}
            hoat_chat = thong_tin_hoat_chat(ho_so) or "Chưa có hoạt chất"
            ham_luong = thong_tin_co_ban.get("hamLuong") or ""
            dang_bao_che = thong_tin_co_ban.get("dangBaoChe") or ""
            print(
                f"{index}. {ho_so.get('tenThuoc', 'Không rõ tên')} "
                f"| SĐK {ho_so.get('soDangKy', 'Không rõ')} "
                f"| {hoat_chat} {ham_luong} | {dang_bao_che}"
            )

        lua_chon_ho_so = input("Chọn hồ sơ thuốc, hoặc Enter để bỏ qua: ").strip()
        if not lua_chon_ho_so:
            continue
        if not lua_chon_ho_so.isdigit() or not 1 <= int(lua_chon_ho_so) <= len(ho_so_thuoc):
            print("Lựa chọn hồ sơ không hợp lệ.")
            continue

        ho_so = ho_so_thuoc[int(lua_chon_ho_so) - 1]
        hoat_chat_dav = thong_tin_hoat_chat(ho_so)
        if not hoat_chat_dav:
            hoat_chat_dav = input("DAV không có hoạt chất; nhập hoạt chất để tra ATC: ").strip()
        if not hoat_chat_dav:
            print("Chưa có hoạt chất để tra mã ATC.")
            continue

        print(f"Hoạt chất từ DAV: {hoat_chat_dav}")
        try:
            ten_chuan, ket_qua = tra_cuu_ma_atc(hoat_chat_dav)
        except requests.RequestException as error:
            ten_chuan = chuan_hoa_ten(hoat_chat_dav)
            ket_qua_cache = doc_cache_atc().get(ten_chuan, [])
            if not ket_qua_cache:
                print(f"Wikidata không phản hồi và chưa có cache cho {ten_chuan}.")
                print(f"Chi tiết kết nối: {error}")
                continue
            ket_qua = [
                (item["ten"], item["ma"])
                for item in ket_qua_cache
                if "ten" in item and "ma" in item
            ]
            print("Wikidata không phản hồi; dùng cache cục bộ, dữ liệu có thể đã cũ.")
        except (KeyError, ValueError) as error:
            print(f"Không đọc được phản hồi Wikidata: {error}")
            continue

        if not ket_qua:
            print("Không tìm thấy mã ATC cho hoạt chất này trên Wikidata.")
            continue

        for index, (ten_wikidata, ma_atc) in enumerate(ket_qua, start=1):
            print(f"{index}. {ma_atc} | {ten_wikidata}")

        print("Một hoạt chất có thể có nhiều mã theo chỉ định hoặc đường dùng.")
        lua_chon_atc = input("Chọn mã ATC để lưu, hoặc Enter để bỏ qua: ").strip()
        if not lua_chon_atc:
            continue
        if not lua_chon_atc.isdigit() or not 1 <= int(lua_chon_atc) <= len(ket_qua):
            print("Lựa chọn mã ATC không hợp lệ; chưa lưu.")
            continue

        ten_wikidata, ma_atc = ket_qua[int(lua_chon_atc) - 1]
        ten_thuoc_dav = ho_so.get("tenThuoc", ten_nhap)
        so_dang_ky = ho_so.get("soDangKy", "")
        thong_tin_co_ban = ho_so.get("thongTinThuocCoBan") or {}
        ham_luong = thong_tin_co_ban.get("hamLuong") or "Chưa có dữ liệu"
        dang_bao_che = thong_tin_co_ban.get("dangBaoChe") or "Chưa có dữ liệu"

        print("\n--- KẾT QUẢ TRA CỨU ---")
        print(f"Tên thuốc: {ten_thuoc_dav}")
        print(f"Hoạt chất chính (DAV): {hoat_chat_dav}")
        print(f"Số đăng ký: {so_dang_ky or 'Chưa có dữ liệu'}")
        print(f"Hàm lượng: {ham_luong}")
        print(f"Dạng bào chế: {dang_bao_che}")
       

        luu_ma_da_chon(
            ten_thuoc_dav,
            so_dang_ky,
            hoat_chat_dav,
            ten_chuan,
            ten_wikidata,
            ma_atc,
        )
        print(f"Đã lưu {ma_atc} vào {FILE_KET_QUA}")

if __name__ == "__main__":
    main()