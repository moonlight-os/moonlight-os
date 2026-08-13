//go:build linux

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const serviceUnit = "/etc/systemd/system/moonlight-os-host-utils.service"

func configDir() string { return "/etc/moonlight-os-host-utils" }

// Where install puts the binary so the unit has something stable to point
// at.  /usr/local/bin is the one place on every distribution that is meant
// for exactly this and is never touched by a package manager.
func installedExePath() string { return "/usr/local/bin/moonlight-os-host-utils" }

func isPrivileged() bool { return os.Geteuid() == 0 }

func privilegeHint() string { return "run this with sudo" }

// Nothing to hide on Linux; the field only exists for the Windows build.
func hideWindow(cmd *exec.Cmd) {}

// findTool locates the usbip binary.
//
// Debian, Arch and Fedora put it on PATH from a package called usbip.
// Ubuntu does not have that package at all -- usbip is inside
// linux-tools-<version>, installed to a versioned directory that is not on
// anyone's PATH, which is the single most common reason "just install usbip"
// fails for people.  So look there too, newest kernel first.
func findTool() (Tool, bool) {
	if p, err := exec.LookPath("usbip"); err == nil {
		return Tool{Path: p, Kind: "usbip"}, true
	}
	candidates := []string{"/usr/sbin/usbip", "/usr/bin/usbip", "/sbin/usbip"}
	if rel, err := os.ReadFile("/proc/sys/kernel/osrelease"); err == nil {
		v := strings.TrimSpace(string(rel))
		candidates = append(candidates,
			"/usr/lib/linux-tools/"+v+"/usbip",
			"/usr/lib/linux-tools-"+v+"/usbip")
	}
	if globbed, err := filepath.Glob("/usr/lib/linux-tools*/usbip"); err == nil {
		candidates = append(candidates, globbed...)
	}
	for _, p := range candidates {
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			return Tool{Path: p, Kind: "usbip"}, true
		}
	}
	return Tool{}, false
}

func needsReboot() bool { return false }

// ensureClient makes this machine able to import USB devices: the vhci-hcd
// module loaded now and at every boot, and a usbip binary to drive it.
func ensureClient() (InstallResult, error) {
	res := InstallResult{Actions: []string{}}

	// vhci-hcd is the virtual host controller -- the thing that makes a
	// remote device show up as a real one.  Without it usbip attach fails
	// with a message about /sys/devices/platform/vhci_hcd that explains
	// nothing to anybody.
	if err := run("modprobe", "vhci-hcd"); err != nil {
		if err2 := run("modprobe", "vhci_hcd"); err2 != nil {
			res.Message = "could not load the vhci-hcd kernel module: " + err.Error()
		} else {
			res.Actions = append(res.Actions, "loaded vhci_hcd")
		}
	} else {
		res.Actions = append(res.Actions, "loaded vhci-hcd")
	}

	const modconf = "/etc/modules-load.d/moonlight-os-host-utils.conf"
	if _, err := os.Stat(modconf); err != nil {
		body := "# Virtual USB host controller, for USB/IP passthrough from Moonlight OS.\nvhci-hcd\n"
		if err := os.WriteFile(modconf, []byte(body), 0o644); err == nil {
			res.Actions = append(res.Actions, "vhci-hcd will load at boot")
		}
	}

	if _, ok := findTool(); !ok {
		if acts, err := installUSBIPPackage(); err != nil {
			res.Actions = append(res.Actions, acts...)
			res.Message = "the usbip client is missing and could not be installed automatically: " + err.Error()
			return res, nil
		} else {
			res.Actions = append(res.Actions, acts...)
		}
	}

	t, ok := findTool()
	res.Installed = ok
	res.ClientTool = ToolInfo{Present: ok, Path: t.Path, Kind: t.Kind}
	if ok {
		res.ClientTool.Version = t.Version()
		if res.Message == "" {
			res.Message = "USB/IP client ready"
		}
	} else if res.Message == "" {
		res.Message = "no usbip binary found after install"
	}
	return res, nil
}

// installUSBIPPackage covers the distributions people actually run a host
// PC on.  Package names diverge more than they should for something that
// ships in the kernel tree.
func installUSBIPPackage() ([]string, error) {
	type mgr struct {
		bin  string
		args [][]string
	}
	kernel := ""
	if rel, err := os.ReadFile("/proc/sys/kernel/osrelease"); err == nil {
		kernel = strings.TrimSpace(string(rel))
	}

	mgrs := []mgr{
		// Debian ships a standalone usbip.  Ubuntu does not, and folds it
		// into the kernel tools instead, so try both spellings under apt.
		{"apt-get", [][]string{
			{"install", "-y", "--no-install-recommends", "usbip"},
			{"install", "-y", "--no-install-recommends", "linux-tools-generic", "linux-tools-" + kernel},
		}},
		{"dnf", [][]string{{"install", "-y", "usbip"}}},
		{"pacman", [][]string{{"-S", "--noconfirm", "--needed", "usbip"}}},
		{"zypper", [][]string{{"install", "-y", "usbip"}}},
		{"apk", [][]string{{"add", "usbip-tools"}}},
	}

	for _, m := range mgrs {
		if _, err := exec.LookPath(m.bin); err != nil {
			continue
		}
		var last error
		for _, args := range m.args {
			if err := run(m.bin, args...); err != nil {
				last = err
				continue
			}
			if _, ok := findTool(); ok {
				return []string{"installed usbip via " + m.bin}, nil
			}
		}
		if last != nil {
			return nil, fmt.Errorf("%s could not install it (%v)", m.bin, last)
		}
		return nil, fmt.Errorf("%s ran but no usbip binary appeared", m.bin)
	}
	return nil, fmt.Errorf("no supported package manager found -- install the usbip package by hand")
}

func installService(exe string, port int) ([]string, error) {
	unit := fmt.Sprintf(`[Unit]
Description=Moonlight OS host utils (USB/IP passthrough agent)
Documentation=https://github.com/MopigamesYT/moonlight-os
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%s run --port %d
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
`, exe, port)

	if err := os.WriteFile(serviceUnit, []byte(unit), 0o644); err != nil {
		return nil, err
	}
	acts := []string{"wrote " + serviceUnit}
	_ = run("systemctl", "daemon-reload")
	if err := run("systemctl", "enable", "--now", "moonlight-os-host-utils"); err != nil {
		return acts, fmt.Errorf("systemctl enable failed: %w", err)
	}
	return append(acts, "enabled and started moonlight-os-host-utils.service"), nil
}

func uninstallService() []string {
	acts := []string{}
	if err := run("systemctl", "disable", "--now", "moonlight-os-host-utils"); err == nil {
		acts = append(acts, "stopped and disabled the service")
	}
	if err := os.Remove(serviceUnit); err == nil {
		acts = append(acts, "removed "+serviceUnit)
		_ = run("systemctl", "daemon-reload")
	}
	return acts
}

// openFirewall is best-effort.  A host PC on a LAN usually has nothing in
// the way; the ones that do are running ufw or firewalld.
func openFirewall(port int) []string {
	p := fmt.Sprintf("%d/tcp", port)
	if _, err := exec.LookPath("ufw"); err == nil {
		if out, _ := output("ufw", "status"); strings.Contains(out, "Status: active") {
			if err := run("ufw", "allow", p); err == nil {
				return []string{"opened " + p + " in ufw"}
			}
		}
	}
	if _, err := exec.LookPath("firewall-cmd"); err == nil {
		if out, _ := output("firewall-cmd", "--state"); strings.TrimSpace(out) == "running" {
			_ = run("firewall-cmd", "--permanent", "--add-port", p)
			if err := run("firewall-cmd", "--reload"); err == nil {
				return []string{"opened " + p + " in firewalld"}
			}
		}
	}
	return nil
}

// Only ever called on Windows; here so main.go does not need build tags.
func setTestSigning(bool) error {
	return fmt.Errorf("not applicable on Linux")
}

func closeFirewall(port int) {
	p := fmt.Sprintf("%d/tcp", port)
	if _, err := exec.LookPath("ufw"); err == nil {
		_ = run("ufw", "delete", "allow", p)
	}
	if _, err := exec.LookPath("firewall-cmd"); err == nil {
		_ = run("firewall-cmd", "--permanent", "--remove-port", p)
		_ = run("firewall-cmd", "--reload")
	}
}
