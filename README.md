# Download Snapchat Memories

Save all your Snapchat memories before the links expire!

---

### **1. Get Your Snapchat Data**
1. Open Snapchat and go to Settings → My Data.
2. Request your Memories and select JSON formatting.
3. Snapchat will email you a link to download a ZIP file containing your memories.

### **2. Run Script**
1. Unbundle the ZIP file you downloaded from snapchat
2. Move the `memories_history.json` and `generate.py` from this github into the same folder
3. cd into that folder
6. Run:
   ```bash
   python3 generate.py
   ```

### **3. View Permanent Memories**
1. Wait to finish downloading
2. Open the new HTML `memories_gallery.html`

**Done!** Everything is saved locally and works offline forever. 🎉
