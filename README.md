# WireGuard – Enigma2 Plugin

WireGuard VPN plugin for Enigma2. Manage WireGuard connections directly from
the remote using `.conf` files placed in `/etc/wireguard/`. Supports full
policy routing via AllowedIPs, domain exclusions and IP/DNS leak tests.

---

## Features

| Button | Action |
|--------|--------|
| **Red** | Close / Back |
| **Green** | Connect selected VPN |
| **Yellow** | Disconnect selected VPN |
| **Blue** | Open Information / Status screen |
| **OK** | Connect / toggle VPN |

### VPN management
- Lists all `.conf` files from `/etc/wireguard/`
- Connect / disconnect individual WireGuard tunnels via `wg-quick`
- Live connection status (active interface, endpoint, bytes transferred)
- Policy routing: AllowedIPs ranges, domain-based split tunneling
- IP/DNS leak test to verify VPN is working correctly

---

## Requirements

- `wireguard-tools` installed on the Enigma2 box
- WireGuard kernel module available (`wireguard-kmod` for OpenPLi)
- Config files in `/etc/wireguard/*.conf`

---

## Build & deploy

```bash
# 1. Copy .env.example to .env and enter your box credentials
cp .env.example .env

# 2. Build the .ipk package
make build

# 3. Build, upload and install on the box
make install

# 4. Restart Enigma2
make restart

# 5. Or do all three steps at once
make deploy
```

The package is placed in `build/enigma2-plugin-extensions-wireguard_1.0.0_all.ipk`.

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Found a bug or have a suggestion for improvement? Please create an issue or pull request.

I appreciate everyone who supports me and the project! For any requests and suggestions, feel free to provide feedback.

<p>
  <a href="https://www.buymeacoffee.com/madoe21">
    <img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" height="50" alt="Buy Me a Coffee">
  </a>

  <a href="https://ko-fi.com/madoe21">
    <img src="https://storage.ko-fi.com/cdn/kofi3.png?v=3" height="50" alt="Ko-fi">
  </a>

  <a href="https://paypal.me/MartinD809">
    <img src="https://www.paypalobjects.com/webstatic/mktg/logo/pp_cc_mark_111x69.jpg" height="50" alt="PayPal">
  </a>
</p>

---

## Built with aiflow

This project was built with support from **[aiflow](https://cyber93de.github.io/aiflow/)** — *built with aiflow*.
