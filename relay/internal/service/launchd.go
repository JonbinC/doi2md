package service

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type launchdManager struct{}

func (launchdManager) Install(binaryPath string, args ...string) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	logPath, err := LogPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(logPath), 0o755); err != nil {
		return err
	}
	label := LabelName()
	plistPath := filepath.Join(home, "Library", "LaunchAgents", label+".plist")
	command := binaryPath
	if len(args) > 0 {
		command = binaryPath + " " + quoteArgs(args)
	}
	plist := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>%s</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/sh</string>
    <string>-lc</string>
    <string>%s >> %s 2>&amp;1</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>%s</string>
  <key>StandardErrorPath</key>
  <string>%s</string>
</dict>
</plist>
`, label, command, logPath, logPath, logPath)
	if err := os.MkdirAll(filepath.Dir(plistPath), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(plistPath, []byte(plist), 0o644); err != nil {
		return err
	}
	uid := os.Getuid()
	_ = exec.Command("launchctl", "bootout", fmt.Sprintf("gui/%d", uid), plistPath).Run()
	return runCommand("launchctl", "bootstrap", fmt.Sprintf("gui/%d", uid), plistPath)
}

func (launchdManager) Uninstall() error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	label := LabelName()
	plistPath := filepath.Join(home, "Library", "LaunchAgents", label+".plist")
	uid := os.Getuid()
	_ = runCommand("launchctl", "bootout", fmt.Sprintf("gui/%d", uid), plistPath)
	return os.Remove(plistPath)
}

func (m launchdManager) Status() (string, error) {
	out, err := exec.Command("launchctl", "print", fmt.Sprintf("gui/%d/%s", os.Getuid(), LabelName())).CombinedOutput()
	if err != nil {
		return "not_installed", nil
	}
	text := string(out)
	if strings.Contains(text, "state = running") {
		return "running", nil
	}
	return "installed", nil
}
