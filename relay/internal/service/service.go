package service

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

type Manager interface {
	Install(binaryPath string, args ...string) error
	Uninstall() error
	Status() (string, error)
}

func New() Manager {
	switch runtime.GOOS {
	case "darwin":
		return launchdManager{}
	case "windows":
		return windowsManager{}
	default:
		return unsupportedManager{goos: runtime.GOOS}
	}
}

func LabelName() string {
	return "com.mdtero.relay"
}

func LogPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	if runtime.GOOS == "windows" {
		base := os.Getenv("LOCALAPPDATA")
		if base == "" {
			base = filepath.Join(home, "AppData", "Local")
		}
		return filepath.Join(base, "mdtero-relay", "relay.log"), nil
	}
	return filepath.Join(home, "Library", "Logs", "mdtero-relay.log"), nil
}

type unsupportedManager struct {
	goos string
}

func (m unsupportedManager) Install(string, ...string) error {
	return fmt.Errorf("background service install is not supported on %s yet; run `mdtero-relay serve` in a terminal", m.goos)
}

func (m unsupportedManager) Uninstall() error {
	return fmt.Errorf("background service uninstall is not supported on %s", m.goos)
}

func (m unsupportedManager) Status() (string, error) {
	return "unsupported", nil
}

func quoteArgs(args []string) string {
	if len(args) == 0 {
		return ""
	}
	parts := make([]string, 0, len(args))
	for _, arg := range args {
		parts = append(parts, shellQuote(arg))
	}
	return strings.Join(parts, " ")
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}
	if !strings.ContainsAny(value, " \t\n'\"\\$") {
		return value
	}
	return "'" + strings.ReplaceAll(value, "'", `'\'"'"'`) + "'"
}

func runCommand(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}
