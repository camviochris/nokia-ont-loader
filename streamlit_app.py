
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Nokia XS-110G-A Loader", layout="centered")
st.title("📦 Nokia XS-110G-A Inventory Uploader")

st.markdown("Upload a CSV file with Serial Number and MAC Address (no headers).")

uploaded_file = st.file_uploader("Choose your Nokia ONT CSV file", type=["csv"])

# Location selector with CUSTOM option
location_option = st.selectbox("Select Inventory Location", ["WAREHOUSE", "CUSTOM"])

custom_location = ""
if location_option == "CUSTOM":
    custom_location = st.text_input("Enter custom location code (e.g., SPFDMO-WH)").strip()

# Proceed if file is uploaded and location is set
if uploaded_file and (location_option == "WAREHOUSE" or custom_location):
    try:
        df = pd.read_csv(uploaded_file, header=None, names=["serial_number", "mac_address"])
        df["device_profile"] = "NOKIA_ONT"
        df["device_name"] = "XS-110G-A"
        df["device_numbers"] = "MAC=" + df["mac_address"] + "|SN=" + df["serial_number"]
        df["inventory_location"] = custom_location if location_option == "CUSTOM" else "WAREHOUSE"
        final_df = df[["device_profile", "device_name", "device_numbers", "inventory_location"]]

        st.success(f"Successfully processed {len(final_df)} ONTs.")
        st.dataframe(final_df)

        csv = final_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Final Inventory File",
            data=csv,
            file_name="nokia_inventory_final.csv",
            mime="text/csv"
        )
    except Exception as e:
        st.error(f"Error processing file: {e}")
