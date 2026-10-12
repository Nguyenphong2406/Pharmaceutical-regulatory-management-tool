import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import csv
import json
import re
from datetime import datetime
from pathlib import Path

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
FILE_KET_QUA = "ma_atc_da_xac_nhan.csv"
TEN_THUOC_TIENg_ANH = {
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
    return TEN_THUOC_TIENg_ANH.get(ten_sach, ten_sach)

def tra_cuu_ma_atc(ten_hoat_chat):
    ten_chuan = chuan_hoa_ten(ten_hoat_chat)
    ten_sparql = json.dumps(ten_chuan)
    query = f"""
    SELECT DISTINCT ?label ?atc WHERE {{
      ?drug wdt:P267 ?atc;
            rdfs:label ?label.
      FILTER(LANG(?label) = "en")
      ?drug (rdfs:label|skos:altLabel) ?matchedName.
      FILTER(LANG(?matchedName) = "en")
      FILTER(LCASE(STR(?matchedName)) = LCASE({ten_sparql}))
    }}
    ORDER BY ?atc
    """
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "PharmacyATCExample/1.0 (educational use)",
    }

    response = requests.get(
        WIKIDATA_ENDPOINT,
        params={"query": query, "format": "json"},
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()

    bindings = response.json().get("results", {}).get("bindings", [])
    ket_qua = {
        (item["label"]["value"], item["atc"]["value"])
        for item in bindings
    }
    return ten_chuan, sorted(ket_qua, key=lambda item: item[1])

def luu_ma_da_chon(ten_nhap, ten_chuan, ten_thuoc, ma_atc):
    file_path = Path(FILE_KET_QUA)
    can_tao_header = not file_path.exists() or file_path.stat().st_size == 0

    with file_path.open("a", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.writer(output_file)
        if can_tao_header:
            writer.writerow(
                ["Tên đã nhập", "Tên chuẩn Wikidata", "Mã ATC", "Nguồn", "Ngày xác nhận"]
            )
        writer.writerow(
            [
                ten_nhap,
                ten_thuoc,
                ma_atc,
                "Wikidata P267 (CC0)",
                datetime.now().date().isoformat(),
            ]
        )

def main():
    print("Tra mã ATC từ Wikidata. Nhập tên hoạt chất; gõ q để thoát.")
    print("Ví dụ: fentanyl, ketamin, halothan. Kết quả chỉ là gợi ý để xác nhận.")

    while True:
        ten_nhap = input("\nTên hoạt chất: ").strip()
        if ten_nhap.casefold() == "q":
            break
        if not ten_nhap:
            continue

        try:
            ten_chuan, ket_qua = tra_cuu_ma_atc(ten_nhap)
        except requests.RequestException as error:
            print(f"Không kết nối được Wikidata: {error}")
            continue
        except (KeyError, ValueError) as error:
            print(f"Không đọc được phản hồi Wikidata: {error}")
            continue

        print(f"Tên gửi tra cứu: {ten_chuan}")
        if not ket_qua:
            print("Không tìm thấy mã. Thử tên hoạt chất tiếng Anh hoặc INN.")
            continue

        for index, (ten_thuoc, ma_atc) in enumerate(ket_qua, start=1):
            print(f"{index}. {ma_atc} | {ten_thuoc}")

        print("Một hoạt chất có thể có nhiều mã theo chỉ định hoặc đường dùng.")
        lua_chon = input("Chọn số để lưu, hoặc Enter để bỏ qua: ").strip()
        if not lua_chon:
            continue

        if not lua_chon.isdigit() or not 1 <= int(lua_chon) <= len(ket_qua):
            print("Lựa chọn không hợp lệ; chưa lưu dữ liệu.")
            continue

        ten_thuoc, ma_atc = ket_qua[int(lua_chon) - 1]
        luu_ma_da_chon(ten_nhap, ten_chuan, ten_thuoc, ma_atc)
        print(f"Đã lưu {ma_atc} vào {FILE_KET_QUA}")

if __name__ == "__main__":
    main()