import re
from datetime import datetime

import pandas as pd
import streamlit as st


st.set_page_config(page_title="📦 Inventory CSV Builder", layout="centered")
st.title("📦 Inventory CSV Builder")

st.markdown(
    "Upload a CSV containing **MAC** and **Serial/SN** values. "
    "You can upload with headers (recommended) or without headers (2 columns)."
)

# --- Company name (used in output filename) ---
company_name = st.text_input(
    "Company name (used in output file name)",
    placeholder="e.g., AcmeFiber"
).strip()

# --- Device profile selector ---
device_profile = st.selectbox("Select device profile", ["NOKIA_ONT", "NOKIA_MESH"])

# --- Device name dropdown (from your inventory list) ---
DEVICE_NAME_OPTIONS = [
    "XS-110G-A",
    "XS-010X-Q",
    "XS-010X-A",
    "Beacon G6",
    "Beacon 6",
    "EMA-XS-2426G-A",
    "EMA-Beacon 2",
    "EMA-XS-2426X-A",
    "EMA-XS-250X-AUSGeneric",
    "EMA-U-090CP-P",
    "EMA-XS-010S-Q",
    "CUST-OWNED-GATEWAY",
    "XS-2426X-A",
    "GS-HT802",
    "GS-HT814",
    "XS-230X-A",
    "Y-010Y-B",
    "GS-HT812",
    "GS-HT818",
    "XS-220X-A",
]
device_name = st.selectbox("Select device name", DEVICE_NAME_OPTIONS)

# --- Inventory location (keep existing behavior) ---
location_option = st.selectbox("Select Inventory Location", ["WAREHOUSE", "CUSTOM"])
custom_location = ""
if location_option == "CUSTOM":
    custom_location = st.text_input("Enter custom location code (e.g., SPFDMO-WH)").strip()

uploaded_file = st.file_uploader("Choose your inventory CSV file", type=["csv"])


def _normalize_company_for_filename(name: str) -> str:
    # Keep it filesystem-friendly: letters, numbers, dash, underscore
    cleaned = re.sub(r"\s+", "_", name.strip())
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", cleaned)
    return cleaned or "company"


def _load_input_csv(file) -> pd.DataFrame:
    """Load CSV robustly. Supports:
    - With headers (mac/serial/sn)
    - Without headers (2 columns: serial, mac) OR (mac, serial)
    """
    # First try reading with headers
    df = pd.read_csv(file, dtype=str)
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    cols_lower = [str(c).strip().lower() for c in df.columns]
    has_mac = any(c in ("mac", "mac_address", "macaddress") for c in cols_lower)
    has_serial = any(c in ("serial", "serial_number", "sn", "s/n", "serialno", "serial_no") for c in cols_lower)

    # If there are exactly 2 columns and they aren't clearly mac/serial, treat as headerless.
    if len(df.columns) == 2 and not (has_mac and has_serial):
        file.seek(0)
        df2 = pd.read_csv(file, header=None, names=["col1", "col2"], dtype=str)
        df2 = df2.applymap(lambda x: x.strip() if isinstance(x, str) else x)

        # Decide which is MAC by simple heuristic
        def looks_like_mac(s: str) -> bool:
            if not isinstance(s, str) or not s:
                return False
            s2 = s.replace(":", "").replace("-", "").lower()
            return len(s2) == 12 and all(ch in "0123456789abcdef" for ch in s2)

        mac_ratio_col1 = df2["col1"].map(looks_like_mac).mean()
        mac_ratio_col2 = df2["col2"].map(looks_like_mac).mean()

        if mac_ratio_col1 >= mac_ratio_col2:
            df = pd.DataFrame({"mac": df2["col1"], "serial": df2["col2"]})
        else:
            df = pd.DataFrame({"mac": df2["col2"], "serial": df2["col1"]})
        return df

    # Headered case: map columns to mac + serial
    mac_col = None
    serial_col = None
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in ("mac", "mac_address", "macaddress"):
            mac_col = c
        if cl in ("serial", "serial_number", "sn", "s/n", "serialno", "serial_no"):
            serial_col = c

    if mac_col is None or serial_col is None:
        raise ValueError(
            "Couldn't find required columns. Please include headers like 'mac' and 'serial' (or 'sn'), "
            "or upload a 2-column headerless CSV."
        )

    return pd.DataFrame({
        "mac": df[mac_col].astype(str).str.strip(),
        "serial": df[serial_col].astype(str).str.strip(),
    })


# Proceed if everything required is present
location_is_set = (location_option == "WAREHOUSE") or bool(custom_location)
if uploaded_file and location_is_set:
    try:
        input_df = _load_input_csv(uploaded_file)

        inventory_location = custom_location if location_option == "CUSTOM" else "WAREHOUSE"

        final_df = pd.DataFrame({
            "device_profile": device_profile,
            "device_name": device_name,
            "device_numbers": "MAC=" + input_df["mac"].astype(str) + "|SN=" + input_df["serial"].astype(str),
            "inventory_location": inventory_location,
            "inventory_status": "unassigned",
        })

        st.success(f"Successfully processed {len(final_df)} devices.")
        st.dataframe(final_df)

        # Output filename: company_date_.csv
        safe_company = _normalize_company_for_filename(company_name)
        date_str = datetime.now().strftime("%Y-%m-%d")
        out_name = f"{safe_company}_{date_str}_.csv"

        csv_bytes = final_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Inventory CSV",
            data=csv_bytes,
            file_name=out_name,
            mime="text/csv",
        )
    except Exception as e:
        st.error(f"Error processing file: {e}")
else:
    st.info("Upload a CSV and choose an inventory location to generate the output file.")
