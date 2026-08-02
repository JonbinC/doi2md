package service

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// systemdManager installs a per-user unit.  It does not require root and is
// suitable for both a Linux desktop and a small server with a user session.
type systemdManager struct{}

func systemdUnitPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".config", "systemd", "user", LabelName()+".service"), nil
}

func (systemdManager) Install(binaryPath string, args ...string) error {
	unitPath, err := systemdUnitPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(unitPath), 0o755); err != nil {
		return err
	}
	command := shellQuote(binaryPath) + " serve"
	if len(args) > 0 {
		command += " " + quoteArgs(args)
	}
	logPath, err := LogPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(logPath), 0o755); err != nil {
		return err
	}
	command += " >> " + shellQuote(logPath) + " 2>&1"
	unit := fmt.Sprintf(`[Unit]
Description=Mdtero campus relay
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/bin/sh -lc %s
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
`, systemdQuote(command))
	if err := os.WriteFile(unitPath, []byte(unit), 0o644); err != nil {
		return err
	}
	if err := runSystemctl("daemon-reload"); err != nil {
		return err
	}
	return runSystemctl("enable", "--now", LabelName()+".service")
}

func (systemdManager) Uninstall() error {
	unitPath, err := systemdUnitPath()
	if err != nil {
		return err
	}
	_ = runSystemctl("disable", "--now", LabelName()+".service")
	if err := os.Remove(unitPath); err != nil && !os.IsNotExist(err) {
		return err
	}
	return runSystemctl("daemon-reload")
}

func (systemdManager) Status() (string, error) {
	cmd := exec.Command("systemctl", "--user", "is-active", LabelName()+".service")
	out, err := cmd.CombinedOutput()
	if err != nil {
		if strings.Contains(strings.ToLower(string(out)), "not found") {
			return "not_installed", nil
		}
		return "installed", nil
	}
	if strings.TrimSpace(string(out)) == "active" {
		return "running", nil
	}
	return "installed", nil
}

func runSystemctl(args ...string) error {
	if _, err := exec.LookPath("systemctl"); err != nil {
		return fmt.Errorf("systemd user service is unavailable; run `mdtero-relay serve` in a terminal")
	}
	cmdArgs := append([]string{"--user"}, args...)
	cmd := exec.Command("systemctl", cmdArgs...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("systemd user service setup failed: %w; run `mdtero-relay serve` in a terminal", err)
	}
	return nil
}

func systemdQuote(value string) string {
	return `"` + strings.NewReplacer(`\`, `\\`, `"`, `\"`, "\n", `\n`).Replace(value) + `"`
}
