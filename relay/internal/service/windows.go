package service

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type windowsManager struct{}

func (windowsManager) Install(binaryPath string, args ...string) error {
	logPath, err := LogPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(logPath), 0o755); err != nil {
		return err
	}
	taskName := "MdteroCampusRelay"
	quotedBinary := `"` + binaryPath + `" serve`
	if len(args) > 0 {
		quotedBinary = `"` + binaryPath + `" serve ` + strings.Join(args, " ")
	}
	command := fmt.Sprintf(
		`schtasks /Create /F /SC ONLOGON /RL LIMITED /TN "%s" /TR "%s >> \"%s\" 2>&1"`,
		taskName,
		quotedBinary,
		logPath,
	)
	cmd := exec.Command("cmd", "/C", command)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {
		return err
	}
	return runCommand("schtasks", "/Run", "/TN", taskName)
}

func (windowsManager) Uninstall() error {
	taskName := "MdteroCampusRelay"
	_ = runCommand("schtasks", "/End", "/TN", taskName)
	return runCommand("schtasks", "/Delete", "/F", "/TN", taskName)
}

func (windowsManager) Status() (string, error) {
	taskName := "MdteroCampusRelay"
	out, err := exec.Command("schtasks", "/Query", "/TN", taskName).CombinedOutput()
	if err != nil {
		return "not_installed", nil
	}
	if strings.Contains(strings.ToLower(string(out)), "running") {
		return "running", nil
	}
	return "installed", nil
}
