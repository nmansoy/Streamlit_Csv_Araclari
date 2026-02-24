import io
import os
import csv
import zipfile
from pathlib import Path
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="CSV Birleştirici", layout="centered")
st.title("🧩 CSV Birleştirici")
st.write("Birden fazla CSV'yi tek bir dosyada birlestirir (tek baslik). Cikti: birlesik CSV + rapor (ZIP olarak indir).")

# -----------------------------
# Ayarlar
# -----------------------------
encoding = st.selectbox("Dosya encoding", ["utf-8", "utf-8-sig", "cp1254", "latin-1"], index=1)
auto_sniff = st.checkbox("Ayirici/format otomatik algila (csv.Sniffer)", value=True)
skip_blank_lines = st.checkbox("Bos satirlari sayma ve yazma", value=True)
strict_header = st.checkbox("Basliklar ayni degilse durdur", value=False)

st.divider()
uploaded = st.file_uploader("CSV dosyalarini yukle (coklu)", type=["csv"], accept_multiple_files=True)

def safe_decode(b: bytes, enc: str) -> str:
    return b.decode(enc, errors="replace")

def sniff_dialect(text: str):
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample)
    except Exception:
        return csv.excel

def read_rows(text: str, dialect):
    f = io.StringIO(text, newline="")
    reader = csv.reader(f, dialect)
    for row in reader:
        yield row

def is_blank_row(row):
    return all((c is None) or (str(c).strip() == "") for c in row)

def count_data_rows(rows_iter, *, skip_blank: bool):
    # rows_iter includes header as first row
    total = 0
    first = True
    for row in rows_iter:
        if first:
            first = False
            continue
        if skip_blank and (not row or is_blank_row(row)):
            continue
        total += 1
    return total

def rows_to_csv_bytes(rows, dialect):
    out = io.StringIO(newline="")
    writer = csv.writer(out, dialect)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")

def build_report(infos, merged_name, total_data_rows, header, warnings):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("CSV Birleştirme Raporu")
    lines.append("=" * 28)
    lines.append(f"Zaman: {ts}")
    lines.append(f"Cikti dosyasi: {merged_name}")
    lines.append("")
    lines.append("Baslik (header):")
    lines.append(header)
    lines.append("")
    lines.append("Dosya bazinda sayimlar (veri satiri):")
    for info in infos:
        lines.append(f"- {info['name']}: {info['data_rows']} veri satiri")
    lines.append("")
    lines.append(f"Birlesim sonucu toplam veri satiri (baslik haric): {total_data_rows}")
    lines.append(f"Birlesim sonucu toplam satir (baslik dahil): {1 + total_data_rows}")
    if warnings:
        lines.append("")
        lines.append("Uyarilar:")
        for w in warnings:
            lines.append(f"- {w}")
    return "\n".join(lines)

def make_output_zip(merged_csv_bytes, merged_csv_name, report_text, report_name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(merged_csv_name, merged_csv_bytes)
        z.writestr(report_name, report_text)
    buf.seek(0)
    return buf.getvalue()

if not uploaded:
    st.info("Baslamak icin birden fazla CSV yukle.")
    st.stop()

# -----------------------------
# Isleme
# -----------------------------
file_infos = []
warnings = []

# İlk dosyanın dialect + header'ı referans
first_bytes = uploaded[0].read()
first_text = safe_decode(first_bytes, encoding)
dialect = sniff_dialect(first_text) if auto_sniff else csv.excel
first_rows = list(read_rows(first_text, dialect))

if not first_rows:
    st.error("Ilk dosya bos gorunuyor.")
    st.stop()

header_row = first_rows[0]
header_str = ",".join(header_row) if dialect.delimiter != "," else ",".join(header_row)

# Başlık kontrolü (gösterim)
st.subheader("🔎 Baslik Onizleme")
st.code(header_str)

# Satır sayımları ve başlık kontrolü
all_data_rows = []  # merged output rows (excluding header)
total_data_rows = 0

def check_header(rows, name):
    if not rows:
        return False, f"{name}: dosya bos."
    h = rows[0]
    if h != header_row:
        msg = f"{name}: baslik farkli (ilk dosya basligi ile ayni degil)."
        return False, msg
    return True, ""

# İlk dosyanın data satırlarını ekle
data_rows_first = first_rows[1:]
if skip_blank_lines:
    data_rows_first = [r for r in data_rows_first if r and not is_blank_row(r)]
all_data_rows.extend(data_rows_first)
data_count_first = len(data_rows_first)
total_data_rows += data_count_first
file_infos.append({"name": uploaded[0].name, "data_rows": data_count_first})

# Diğer dosyalar
for up in uploaded[1:]:
    b = up.read()
    text = safe_decode(b, encoding)
    d = sniff_dialect(text) if auto_sniff else csv.excel

    # Dialect farklıysa uyarı (delimiter değişebilir)
    if (d.delimiter, d.quotechar, d.escapechar) != (dialect.delimiter, dialect.quotechar, dialect.escapechar):
        warnings.append(f"{up.name}: CSV formati farkli olabilir (delimiter/quote ayarlari). Yine de okundu.")

    rows = list(read_rows(text, d))

    ok, msg = check_header(rows, up.name)
    if not ok:
        if strict_header:
            st.error(msg + " (strict mode acik)")
            st.stop()
        else:
            warnings.append(msg + " (strict kapali: dosya yine de birlestirildi)")

    data_rows = rows[1:]
    if skip_blank_lines:
        data_rows = [r for r in data_rows if r and not is_blank_row(r)]

    all_data_rows.extend(data_rows)
    file_infos.append({"name": up.name, "data_rows": len(data_rows)})
    total_data_rows += len(data_rows)

# -----------------------------
# Çıktı üret
# -----------------------------
ts_name = datetime.now().strftime("%Y%m%d%H%M")
merged_csv_name = f"Birlesik_CSV_{ts_name}.csv"
report_name = f"Sonuc_Raporu_{ts_name}.txt"

merged_rows = [header_row] + all_data_rows
merged_csv_bytes = rows_to_csv_bytes(merged_rows, dialect)

report_text = build_report(
    infos=file_infos,
    merged_name=merged_csv_name,
    total_data_rows=total_data_rows,
    header=",".join(header_row),
    warnings=warnings
)

st.subheader("📊 Ozet")
st.write(f"Toplam dosya: **{len(uploaded)}**")
st.write(f"Toplam veri satiri (baslik haric): **{total_data_rows}**")

with st.expander("Dosya bazinda sayimlar"):
    st.table([{ "Dosya": i["name"], "Veri satiri": i["data_rows"] } for i in file_infos])

if warnings:
    with st.expander("Uyarilar"):
        for w in warnings:
            st.warning(w)

st.subheader("⬇️ Indirme")
out_zip = make_output_zip(merged_csv_bytes, merged_csv_name, report_text, report_name)
st.download_button(
    "Birlesik CSV + Rapor (ZIP) indir",
    data=out_zip,
    file_name=f"csv_birlesim_{ts_name}.zip",
    mime="application/zip"
)

with st.expander("Raporu goruntule"):
    st.text(report_text)

with st.expander("Birlesik CSV onizleme (ilk 200 satir)"):
    # Pandas kullanmadan basit onizleme: ilk 200 satiri metin olarak
    preview_lines = merged_csv_bytes.decode("utf-8", errors="replace").splitlines()[:200]
    st.text("\n".join(preview_lines))
