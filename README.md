# 📸 Download Snapchat Memories

Save all your Snapchat memories before the links expire!

---

## ⚡️ Quick Start (5 minutes)

### **1. Get Your Snapchat Data**
1. Open Snapchat and go to Settings → My Data.
2. Request your Memories and select JSON formatting.
3. Snapchat will email you a link to download a ZIP file containing your memories.

### **2. Run Script**
1. Create a folder in your desktop called snapchat-memories-download
2. Open the ZIP file you downloaded from snapchat, then open the json folder
3. Drag and drop your `memories_history.json` and `generate.py` from this github into snapchat-memories-download
4. Open Terminal (Mac) or Command Prompt (Windows)
5. Navigate to that folder by entering in the terminal:
   ```bash
   cd path/to/your/folder
   ```
   In this case (if you made the folder in desktop):
   ```bash
   cd desktop/snapchat-memories-download
   ```
6. Run:
   ```bash
   python3 generate.py
   ```

### **3. View Permanent Memories**
1. Wait to finish downloading
2. Open the new HTML `memories_gallery.html`

**Done!** Everything is saved locally and works offline forever. 🎉

---
