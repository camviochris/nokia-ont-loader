
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Nokia XS-110G-A Loader", layout="centered")
st.title("📦 Nokia XS-110G-A Inventory Uploader")

st.markdown("Upload a CSV file with Serial Number and MAC Address (no headers).")

uploaded_file = st.file_uploader("Choose your Nokia ONT CSV file", type=["csv"])

if uploaded_file:
    try:
        # Read CSV with no headers, assume format [SN, MAC]
        df = pd.read_csv(uploaded_file, header=None, names=["serial_number", "mac_address"])

        # Build required output columns
        df["device_profile"] = "NOKIA_ONT"
        df["device_name"] = "XS-110G-A"
        df["device_numbers"] = "MAC=" + df["mac_address"] + "|SN=" + df["serial_number"]
        df["inventory_location"] = "SPFDMO-WH"

        # Reorder and select final columns
        final_df = df[["device_profile", "device_name", "device_numbers", "inventory_location"]]

        st.success(f"Successfully processed {len(final_df)} ONTs.")
        st.dataframe(final_df)

        # Allow export
        csv = final_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Final Inventory File",
            data=csv,
            file_name="nokia_inventory_final.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"Error processing file: {e}")
