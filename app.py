import io
import csv
import zipfile
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="CSV Birleştirici", layout="centered")
st.title("🧩 CSV Birleştirici")

st.write("Birden fazla CSV dosyasını tek bir dosyada birleştirir. Çıktı: Birleşik CSV + Rapor (ZIP).")

# Büyük field hatalarını önlemek için limit artır
try:
    csv.field_size_limit(1024 * 1024 * 64)
except Exception:
    pass

st.divider()

# -----------------------------
# Ayarlar
# -----------------------------
encoding = st.selectbox("Dosya encoding", ["utf-8", "utf-8-sig", "cp1254", "latin-1"], index=1)

mode = st.radio(
    "Delimiter seçimi",
    ["Otomatik algıla", "Manuel seç"],
    horizontal=True
)

manual_delim = st.selectbox("Manuel delimiter", [",", ";", "\\t", "|"], index=0, disabled=(mode != "Manuel seç"))
manual_delim = "\t" if manual_delim == "\\t" else manual_delim

quotechar = st.selectbox("Quote char", ['"', "'"], index=0)

skip_blank_lines = st.checkbox("Boş satırları atla", value=True)
strict_header = st.checkbox("Header farklıysa işlemi durdur (strict)", value=False)

st.divider()
uploaded = st.file_uploader("CSV dosyalarını yükle (en az 2)", type=["csv"], accept_multiple_files=True)

if not uploaded or len(uploaded) < 2:
    st.info("Devam etmek için en az 2 CSV yükleyin.")
    st.stop()


# -----------------------------
# Yardımcı Fonksiyonlar
# -----------------------------
def safe_decode(b, enc):
    return b.decode(enc, errors="replace").replace("\x00", "")


def guess_delimiter(text):
    sample_lines = [ln for ln in text.splitlines()[:25] if ln.strip()]
    if not sample_lines:
        return ","
    candidates = [",", ";", "\t", "|"]
    best = ","
    best_score = -1
    for d in candidates:
        counts = [len(ln.split(d)) for ln in sample_lines]
        avg = sum(counts) / len(counts)
        var = sum((c - avg) ** 2 for c in counts) / len(counts)
        score = avg - var
        if score > best_score:
            best_score = score
            best = d
    return best


def make_dialect(text):
    if mode == "Manuel seç":
        d = csv.excel
        d.delimiter = manual_delim
        d.quotechar = quotechar
        return d

    try:
        return csv.Sniffer().sniff(text[:4096])
    except Exception:
        d = csv.excel
        d.delimiter = guess_delimiter(text)
        d.quotechar = quotechar
        return d


def is_blank_row(row):
    return all(str(c).strip() == "" for c in row)


def rows_to_bytes(rows, dialect):
    out = io.StringIO(newline="")
    writer = csv.writer(out, dialect)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


# -----------------------------
# İşlem Başlıyor
# -----------------------------
warnings = []
errors = []
file_infos = []

# İlk dosya referans
first_text = safe_decode(uploaded[0].read(), encoding)
first_dialect = make_dialect(first_text)

try:
    first_rows = list(csv.reader(io.StringIO(first_text), first_dialect))
except Exception as e:
    st.error(f"İlk dosya okunamadı: {e}")
    st.stop()

if not first_rows:
    st.error("İlk dosya boş.")
    st.stop()

header = first_rows[0]

st.subheader("🔎 Header Önizleme")
st.code(",".join(header))

all_data_rows = []
total_data_rows = 0

# İlk dosya veri
data_rows = first_rows[1:]
if skip_blank_lines:
    data_rows = [r for r in data_rows if r and not is_blank_row(r)]

all_data_rows.extend(data_rows)
file_infos.append({"name": uploaded[0].name, "rows": len(data_rows)})
total_data_rows += len(data_rows)


# Diğer dosyalar
for up in uploaded[1:]:
    text = safe_decode(up.read(), encoding)
    d = make_dialect(text)

    try:
        rows = list(csv.reader(io.StringIO(text), d))
    except Exception as e:
        errors.append(f"{up.name} okunamadı: {e}")
        continue

    if not rows:
        errors.append(f"{up.name} boş dosya.")
        continue

    if rows[0] != header:
        msg = f"{up.name} header farklı."
        if strict_header:
            st.error(msg)
            st.stop()
        warnings.append(msg)

    drows = rows[1:]
    if skip_blank_lines:
        drows = [r for r in drows if r and not is_blank_row(r)]

    all_data_rows.extend(drows)
    file_infos.append({"name": up.name, "rows": len(drows)})
    total_data_rows += len(drows)


if not all_data_rows:
    st.error("Hiç veri satırı oluşmadı.")
    st.stop()

# -----------------------------
# Çıktı Oluştur
# -----------------------------
ts = datetime.now().strftime("%Y%m%d%H%M")
merged_name = f"Birlesik_CSV_{ts}.csv"
report_name = f"Rapor_{ts}.txt"

merged_rows = [header] + all_data_rows
merged_bytes = rows_to_bytes(merged_rows, first_dialect)

report_lines = []
report_lines.append("CSV Birleştirme Raporu")
report_lines.append("=" * 30)
report_lines.append(f"Toplam dosya: {len(uploaded)}")
report_lines.append(f"Toplam veri satırı (header hariç): {total_data_rows}")
report_lines.append("")

for info in file_infos:
    report_lines.append(f"{info['name']}: {info['rows']} veri satırı")

if warnings:
    report_lines.append("\nUyarılar:")
    report_lines.extend(warnings)

if errors:
    report_lines.append("\nHatalar:")
    report_lines.extend(errors)

report_text = "\n".join(report_lines)

# ZIP oluştur
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr(merged_name, merged_bytes)
    z.writestr(report_name, report_text)

buf.seek(0)

st.subheader("📊 Özet")
st.write(f"Toplam veri satırı: **{total_data_rows}**")

st.download_button(
    "⬇️ Birleşik CSV + Rapor (ZIP) indir",
    data=buf.getvalue(),
    file_name=f"csv_birlesim_{ts}.zip",
    mime="application/zip"
)

with st.expander("Raporu Görüntüle"):
    st.text(report_text)
