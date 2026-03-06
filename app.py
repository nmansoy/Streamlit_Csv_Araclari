import io
import os
import csv
import zipfile
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="CSV Araçları", layout="centered")
st.title("🧰 CSV Araçları")

st.markdown("""
Bu uygulama birden fazla CSV işlemini tek yerde toplar.

### Mevcut araçlar
- **CSV içindeki çift tırnakları kaldır**
- **Birden fazla CSV dosyasını birleştir**

Daha sonra buna yeni araçlar da eklenebilir.
""")

# Büyük alan hatalarını önlemek için
try:
    csv.field_size_limit(1024 * 1024 * 64)
except Exception:
    pass


# =========================================================
# ORTAK YARDIMCI FONKSİYONLAR
# =========================================================
def safe_decode(data: bytes, encoding: str) -> str:
    return data.decode(encoding, errors="replace").replace("\x00", "")


def build_output_zip(results, report_text: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("rapor.txt", report_text)
        for out_name, out_bytes in results:
            z.writestr(out_name, out_bytes)
    out.seek(0)
    return out.getvalue()


def iter_csv_from_uploaded_zip(zip_bytes: bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for name in zf.namelist():
            if name.lower().endswith(".csv") and not name.endswith("/"):
                yield name, zf.read(name)


def is_blank_row(row):
    return all(str(c).strip() == "" for c in row)


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


def rows_to_bytes(rows, dialect):
    out = io.StringIO(newline="")
    writer = csv.writer(out, dialect)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


# =========================================================
# 1) CSV İÇİNDEKİ TIRNAKLARI KALDIR
# =========================================================
def process_csv_remove_quotes(data: bytes, filename: str, *, auto_sniff: bool, encoding: str):
    """
    Returns:
      out_bytes (bytes): modified CSV content (utf-8)
      modified (bool)
      lines_modified (int)
      error (str | None)
    """
    try:
        text = safe_decode(data, encoding)
        sample = text[:4096]

        if auto_sniff:
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
        else:
            dialect = csv.excel

        infile = io.StringIO(text, newline="")
        reader = csv.reader(infile, dialect)

        new_rows = []
        modified = False
        lines_modified = 0

        for row in reader:
            new_row = [cell.replace('"', "") for cell in row]
            new_rows.append(new_row)
            if new_row != row:
                modified = True
                lines_modified += 1

        out_buf = io.StringIO(newline="")
        writer = csv.writer(out_buf, dialect)
        writer.writerows(new_rows)

        return out_buf.getvalue().encode("utf-8"), modified, lines_modified, None

    except Exception as e:
        return b"", False, 0, f"{filename}: {e}"


def render_remove_quotes_page():
    st.header('🧹 CSV içindeki " karakterlerini kaldır')

    st.markdown("""
    Bu araç yüklediğin CSV dosyalarının (veya CSV içeren bir ZIP'in) içindeki
    **çift tırnak** (`"`) karakterlerini hücrelerden siler.

    - Değişiklik olan dosyalar: `modified_<orijinal_ad>.csv`
    - Değişiklik olmayanlar raporda listelenir
    - Sonuçlar tek bir ZIP olarak indirilebilir
    """)

    source_mode = st.radio(
        "Girdi türü",
        ["CSV dosyaları yükle (çoklu)", "CSV içeren ZIP yükle (alt klasörler dahil)"],
        horizontal=True,
        key="remove_quotes_source_mode"
    )

    auto_sniff = st.checkbox(
        "Ayırıcıyı otomatik algıla (csv.Sniffer)",
        value=True,
        key="remove_quotes_auto_sniff"
    )

    encoding = st.selectbox(
        "Dosya encoding",
        ["utf-8", "utf-8-sig", "cp1254", "latin-1"],
        index=1,
        key="remove_quotes_encoding"
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    quote_char = '"'

    modified_lines = []
    unchanged_lines = []
    errors = []
    output_files = []

    if source_mode == "CSV dosyaları yükle (çoklu)":
        uploaded = st.file_uploader(
            "CSV dosyalarını yükle",
            type=["csv"],
            accept_multiple_files=True,
            key="remove_quotes_csv_uploader"
        )

        if uploaded:
            for up in uploaded:
                data = up.read()
                out_bytes, modified, lines_modified, err = process_csv_remove_quotes(
                    data, up.name, auto_sniff=auto_sniff, encoding=encoding
                )

                if err:
                    errors.append(err)
                    continue

                out_name = f"modified_{os.path.basename(up.name)}"
                output_files.append((out_name, out_bytes))

                if modified:
                    modified_lines.append(
                        f"{up.name} dosyasında {lines_modified} satırda {quote_char!r} karakteri silindi."
                    )
                else:
                    unchanged_lines.append(f"{up.name} dosyasında değişiklik yapılmadı.")

    else:
        upzip = st.file_uploader(
            "CSV içeren ZIP dosyasını yükle",
            type=["zip"],
            accept_multiple_files=False,
            key="remove_quotes_zip_uploader"
        )

        if upzip is not None:
            zip_bytes = upzip.read()
            try:
                found_any = False
                for member_name, member_bytes in iter_csv_from_uploaded_zip(zip_bytes):
                    found_any = True
                    base_name = os.path.basename(member_name)

                    out_bytes, modified, lines_modified, err = process_csv_remove_quotes(
                        member_bytes, member_name, auto_sniff=auto_sniff, encoding=encoding
                    )

                    if err:
                        errors.append(err)
                        continue

                    folder = os.path.dirname(member_name)
                    out_file_name = f"modified_{base_name}"
                    out_name = os.path.join(folder, out_file_name) if folder else out_file_name

                    output_files.append((out_name, out_bytes))

                    if modified:
                        modified_lines.append(
                            f"{member_name} dosyasında {lines_modified} satırda {quote_char!r} karakteri silindi."
                        )
                    else:
                        unchanged_lines.append(f"{member_name} dosyasında değişiklik yapılmadı.")

                if not found_any:
                    st.warning("ZIP içinde CSV bulunamadı.")

            except zipfile.BadZipFile:
                st.error("Geçersiz veya bozuk ZIP dosyası.")
            except Exception as e:
                st.error(f"Hata: {e}")

    if output_files or errors or modified_lines or unchanged_lines:
        report = []
        report.append("CSV Dosyalarında Yapılan Değişiklikler\n\n")
        report.append(f"Zaman: {timestamp}\n")

        if modified_lines:
            report.append("\nDeğişiklik Yapılan Dosyalar:\n")
            report.extend([line + "\n" for line in modified_lines])

        if unchanged_lines:
            report.append("\nDeğişiklik Yapılmayan Dosyalar:\n")
            report.extend([line + "\n" for line in unchanged_lines])

        if errors:
            report.append("\nHatalar:\n")
            report.extend([line + "\n" for line in errors])

        report_text = "".join(report)

        st.subheader("📄 Rapor")
        st.text(report_text)

        if output_files:
            out_zip_bytes = build_output_zip(output_files, report_text)
            st.download_button(
                "📥 Çıktıları indir (ZIP)",
                data=out_zip_bytes,
                file_name=f"modified_csvler_{timestamp}.zip",
                mime="application/zip"
            )

            with st.expander("Tek tek dosya indirme"):
                for name, b in output_files:
                    st.download_button(
                        f"⬇️ {name}",
                        data=b,
                        file_name=os.path.basename(name),
                        mime="text/csv",
                        key=f"dl_{name}"
                    )


# =========================================================
# 2) CSV BİRLEŞTİRİCİ
# =========================================================
def make_dialect_for_merge(text, mode, manual_delim, quotechar):
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


def render_merge_csv_page():
    st.header("🧩 CSV Birleştirici")
    st.write("Birden fazla CSV dosyasını tek bir dosyada birleştirir. Çıktı: Birleşik CSV + Rapor (ZIP).")

    encoding = st.selectbox(
        "Dosya encoding",
        ["utf-8", "utf-8-sig", "cp1254", "latin-1"],
        index=1,
        key="merge_encoding"
    )

    mode = st.radio(
        "Delimiter seçimi",
        ["Otomatik algıla", "Manuel seç"],
        horizontal=True,
        key="merge_mode"
    )

    manual_delim = st.selectbox(
        "Manuel delimiter",
        [",", ";", "\\t", "|"],
        index=0,
        disabled=(mode != "Manuel seç"),
        key="merge_manual_delim"
    )
    manual_delim = "\t" if manual_delim == "\\t" else manual_delim

    quotechar = st.selectbox(
        "Quote char",
        ['"', "'"],
        index=0,
        key="merge_quotechar"
    )

    skip_blank_lines = st.checkbox(
        "Boş satırları atla",
        value=True,
        key="merge_skip_blank"
    )

    strict_header = st.checkbox(
        "Header farklıysa işlemi durdur (strict)",
        value=False,
        key="merge_strict_header"
    )

    uploaded = st.file_uploader(
        "CSV dosyalarını yükle (en az 2)",
        type=["csv"],
        accept_multiple_files=True,
        key="merge_uploader"
    )

    if not uploaded:
        st.info("Devam etmek için en az 2 CSV yükleyin.")
        return

    if len(uploaded) < 2:
        st.warning("Birleştirme için en az 2 CSV dosyası gerekli.")
        return

    warnings = []
    errors = []
    file_infos = []

    first_text = safe_decode(uploaded[0].read(), encoding)
    first_dialect = make_dialect_for_merge(first_text, mode, manual_delim, quotechar)

    try:
        first_rows = list(csv.reader(io.StringIO(first_text), first_dialect))
    except Exception as e:
        st.error(f"İlk dosya okunamadı: {e}")
        return

    if not first_rows:
        st.error("İlk dosya boş.")
        return

    header = first_rows[0]

    st.subheader("🔎 Header Önizleme")
    st.code(",".join(header))

    all_data_rows = []
    total_data_rows = 0

    data_rows = first_rows[1:]
    if skip_blank_lines:
        data_rows = [r for r in data_rows if r and not is_blank_row(r)]

    all_data_rows.extend(data_rows)
    file_infos.append({"name": uploaded[0].name, "rows": len(data_rows)})
    total_data_rows += len(data_rows)

    for up in uploaded[1:]:
        text = safe_decode(up.read(), encoding)
        d = make_dialect_for_merge(text, mode, manual_delim, quotechar)

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
                return
            warnings.append(msg)

        drows = rows[1:]
        if skip_blank_lines:
            drows = [r for r in drows if r and not is_blank_row(r)]

        all_data_rows.extend(drows)
        file_infos.append({"name": up.name, "rows": len(drows)})
        total_data_rows += len(drows)

    if not all_data_rows:
        st.error("Hiç veri satırı oluşmadı.")
        return

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


# =========================================================
# ANA MENÜ
# =========================================================
tool = st.selectbox(
    "Yapmak istediğin işlemi seç",
    [
        "CSV içindeki çift tırnakları kaldır",
        "CSV dosyalarını birleştir",
    ]
)

if tool == "CSV içindeki çift tırnakları kaldır":
    render_remove_quotes_page()

elif tool == "CSV dosyalarını birleştir":
    render_merge_csv_page()
