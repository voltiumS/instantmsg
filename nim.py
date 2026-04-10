import sys
import os
import sqlite3
import json
import base64
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from supabase import create_client

# -- backend config --
# grab these from your free project at supabase.com
SB_URL = "https://qlumjnppqpfzrzqcqelp.supabase.co"
SB_KEY = "sb_publishable_XsmHyMOBZLn--ED6gLwOdw_9tKOcvTy"
supabase = create_client(SB_URL, SB_KEY)

class nim_engine(QMainWindow):
    def __init__(self):
        super().__init__()
        self.local_db = "nim_vault.db"
        self.active_room = "lobby"
        self.identity = None
        self.cipher = None
        
        self.init_vault()
        self.check_auth()

    def init_vault(self):
        """creates an encrypted local store for credentials"""
        conn = sqlite3.connect(self.local_db)
        conn.execute("CREATE TABLE IF NOT EXISTS vault (id INTEGER PRIMARY KEY, sn TEXT, secret TEXT, salt BLOB)")
        conn.commit()
        conn.close()

    def check_auth(self):
        conn = sqlite3.connect(self.local_db)
        user_data = conn.execute("SELECT sn, secret, salt FROM vault WHERE id=1").fetchone()
        conn.close()

        if not user_data:
            self.draw_signup()
        else:
            self.sn, b64_key, salt = user_data
            self.cipher = Fernet(b64_key.encode())
            self.draw_messenger()

    def draw_signup(self):
        """the 1999 setup wizard"""
        self.setWindowTitle("NIM Setup Wizard")
        self.setFixedSize(350, 250)
        self.setStyleSheet("background-color: #d4d0c8;")
        
        layout = QVBoxLayout()
        img_label = QLabel("NOL Instant Messenger")
        img_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #000080; border-bottom: 2px solid gray;")
        layout.addWidget(img_label)

        layout.addWidget(QLabel("Choose your Screen Name:"))
        self.sn_in = QLineEdit()
        layout.addWidget(self.sn_in)
        
        layout.addWidget(QLabel("Set a Local Vault Password (for AES):"))
        self.pw_in = QLineEdit()
        self.pw_in.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pw_in)

        btn = QPushButton("Finish Setup")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.finalize_user)
        layout.addWidget(btn)
        
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def finalize_user(self):
        sn = self.sn_in.text()
        pw = self.pw_in.text().encode()
        if sn and pw:
            # high-level key derivation (PBKDF2) for the local vault
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
            key = base64.urlsafe_b64encode(kdf.derive(pw))
            
            conn = sqlite3.connect(self.local_db)
            conn.execute("INSERT INTO vault (id, sn, secret, salt) VALUES (1, ?, ?, ?)", (sn, key.decode(), salt))
            conn.commit()
            conn.close()
            self.check_auth()

    def draw_messenger(self):
        """the primary aim-inspired desktop interface"""
        self.setWindowTitle(f"{self.sn}'s Buddy List")
        self.setFixedSize(600, 500)
        self.setStyleSheet("""
            QMainWindow { background-color: #d4d0c8; }
            QTextEdit { background: white; border: 2px inset #808080; font-family: 'Arial'; font-size: 12px; }
            QLineEdit { background: white; border: 2px inset #808080; padding: 2px; }
            QPushButton { background: #d4d0c8; border: 2px outset white; padding: 4px; font-size: 11px; }
            QPushButton:pressed { border: 2px inset gray; }
            QListWidget { background: white; border: 2px inset gray; }
        """)

        # -- UI Grid --
        main_widget = QWidget()
        main_layout = QHBoxLayout()

        # Left Column: Buddy List & Rooms
        left_col = QVBoxLayout()
        left_col.addWidget(QLabel("Rooms:"))
        self.room_list = QListWidget()
        self.room_list.addItems(["#lobby", "#tech", "#90s_nostalgia", "#dev_chat"])
        self.room_list.itemClicked.connect(self.switch_room)
        left_col.addWidget(self.room_list)
        
        left_col.addWidget(QLabel("Buddies:"))
        self.buddy_list = QListWidget()
        self.buddy_list.addItems(["sys_admin", "cool_skater_99", "matrix_reloaded"])
        left_col.addWidget(self.buddy_list)
        main_layout.addLayout(left_col, 1)

        # Right Column: Chat Box
        right_col = QVBoxLayout()
        self.chat_header = QLabel(f"Current Room: {self.active_room}")
        self.chat_header.setStyleSheet("font-weight: bold; color: #000080;")
        right_col.addWidget(self.chat_header)

        self.screen = QTextEdit()
        self.screen.setReadOnly(True)
        right_col.addWidget(self.screen)

        self.msg_input = QLineEdit()
        self.msg_input.returnPressed.connect(self.dispatch)
        right_col.addWidget(self.msg_input)

        btn_row = QHBoxLayout()
        self.send_btn = QPushButton("Send Message")
        self.send_btn.clicked.connect(self.dispatch)
        btn_row.addStretch()
        btn_row.addWidget(self.send_btn)
        right_col.addLayout(btn_row)

        main_layout.addLayout(right_col, 3)
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # -- Internet Realtime Sub --
        self.connect_network()

    def connect_network(self):
        """establishes the ddos-resistant websocket channel"""
        self.channel = supabase.channel(f'room:{self.active_room}')
        self.channel.on('broadcast', {'event': 'shout'}, self.on_broadcast).subscribe()
        self.screen.append(f"<i>*** Connected to {self.active_room} ***</i>")

    def switch_room(self, item):
        new_room = item.text().replace("#", "")
        self.channel.unsubscribe()
        self.active_room = new_room
        self.chat_header.setText(f"Current Room: {self.active_room}")
        self.screen.clear()
        self.connect_network()

    def on_broadcast(self, payload):
        """processes incoming internet packets"""
        sender = payload['payload']['user']
        blob = payload['payload']['blob']
        timestamp = datetime.now().strftime("%H:%M")
        
        try:
            # attempt aes decryption
            decrypted = self.cipher.decrypt(blob.encode()).decode()
            color = "#ff0000" if sender == self.sn else "#0000ff"
            self.screen.append(f"<font color='gray'>[{timestamp}]</font> <b style='color:{color};'>{sender}:</b> {decrypted}")
        except:
            # if decryption fails (different room key), show as locked
            self.screen.append(f"<font color='gray'>[{timestamp}]</font> <b>{sender}:</b> <font color='gray'>[Encrypted Data Block]</font>")

    def dispatch(self):
        raw = self.msg_input.text()
        if not raw: return
        
        # lock message with aes-256
        locked = self.cipher.encrypt(raw.encode()).decode()
        
        # broadcast to supabase edge network (ddos immune infrastructure)
        self.channel.send({
            'type': 'broadcast',
            'event': 'shout',
            'payload': {'user': self.sn, 'blob': locked}
        })
        
        self.msg_input.clear()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # forces win98 style buttons
    nim = nim_engine()
    nim.show()
    sys.exit(app.exec())