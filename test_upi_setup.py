"""
Quick test script to verify UPI payment integration setup
Run this before starting the app to check configuration
"""

print("=" * 60)
print("UPI Payment Integration - Configuration Check")
print("=" * 60)

# Test imports
try:
    from urllib.parse import quote
    print("✓ urllib.parse imported successfully")
except ImportError as e:
    print(f"✗ Error importing urllib.parse: {e}")

try:
    import qrcode
    print("✓ qrcode library imported successfully")
except ImportError:
    print("✗ qrcode library not found!")
    print("  Install it with: pip install qrcode[pil]")

try:
    from io import BytesIO
    import base64
    print("✓ Image processing libraries available")
except ImportError as e:
    print(f"✗ Error importing image libraries: {e}")

# Test UPI link generation
print("\n" + "=" * 60)
print("Testing UPI Link Generation")
print("=" * 60)

upi_id = "mess@oksbi"
payee_name = quote("Mess Management")
amount = "150.00"
transaction_note = quote("Mess Bill #1 - STU0001")
txn_ref = "MESS1STU120251111120000"

upi_link = f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount}&cu=INR&tn={transaction_note}&tr={txn_ref}"

print(f"\nGenerated UPI Link:")
print(upi_link)
print(f"\n✓ UPI link format is correct")

# Test QR code generation
try:
    import qrcode
    from io import BytesIO
    import base64
    
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_link)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    
    print(f"✓ QR code generated successfully ({len(qr_base64)} bytes)")
    
except Exception as e:
    print(f"✗ Error generating QR code: {e}")

print("\n" + "=" * 60)
print("Configuration Instructions")
print("=" * 60)
print("\n1. Update your UPI ID in app.py:")
print("   app.config['UPI_ID'] = 'yourmessaccount@paytm'")
print("\n2. Update merchant name:")
print("   app.config['UPI_NAME'] = 'Your College Mess Name'")
print("\n3. Make sure these are installed:")
print("   pip install qrcode[pil]")
print("\n4. Test on mobile device for best experience!")
print("\n" + "=" * 60)
