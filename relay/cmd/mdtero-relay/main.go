package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mdtero/mdtero-relay/internal/auth"
	"github.com/mdtero/mdtero-relay/internal/browserfetch"
	"github.com/mdtero/mdtero-relay/internal/client"
	"github.com/mdtero/mdtero-relay/internal/config"
	"github.com/mdtero/mdtero-relay/internal/service"
)

const version = "0.1.2"

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(2)
	}

	switch os.Args[1] {
	case "serve":
		os.Exit(runServe(os.Args[2:]))
	case "status":
		os.Exit(runStatus(os.Args[2:]))
	case "login":
		os.Exit(runLogin(os.Args[2:]))
	case "browser-open":
		os.Exit(runBrowserOpen(os.Args[2:]))
	case "install":
		os.Exit(runInstall(os.Args[2:]))
	case "uninstall":
		os.Exit(runUninstall(os.Args[2:]))
	case "version", "-v", "--version":
		fmt.Println("mdtero-relay", version)
	case "help", "-h", "--help":
		printUsage()
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n\n", os.Args[1])
		printUsage()
		os.Exit(2)
	}
}

func printUsage() {
	fmt.Print(`Mdtero campus relay — keep one command running on a campus-network machine.

Usage:
  mdtero-relay install [--api-key <key>] [--label <name>]
  mdtero-relay serve [--label <name>]
  mdtero-relay status
  mdtero-relay login [--browser] [--api-key <key>] [--label <name>]
  mdtero-relay browser-open <publisher-url>
  mdtero-relay uninstall
  mdtero-relay version

One-line install:
  macOS:   curl -fsSL https://mdtero.com/relay | bash
  Windows: irm https://mdtero.com/relay.ps1 | iex
`)
}

func runBrowserOpen(args []string) int {
	if len(args) != 1 || strings.TrimSpace(args[0]) == "" {
		fmt.Fprintln(os.Stderr, "Usage: mdtero-relay browser-open <publisher-url>")
		return 2
	}
	browser := browserfetch.FromEnv()
	if browser == nil || !browser.Enabled() {
		fmt.Fprintln(os.Stderr, "Authorized browser capture is not configured on this relay.")
		return 1
	}
	result := browser.Prepare(context.Background(), strings.TrimSpace(args[0]), 120*time.Second)
	if result.Error != "" || result.ReasonCode != "" {
		message := strings.TrimSpace(result.Error)
		if message == "" {
			message = strings.TrimSpace(result.ReasonCode)
		}
		if message == "" {
			message = "Could not open the authorized browser."
		}
		fmt.Fprintln(os.Stderr, message)
		return 1
	}
	fmt.Println("Mdtero Access browser is ready. Complete any institution sign-in or publisher challenge there, then retry the paper task.")
	return 0
}

func runServe(args []string) int {
	fs := flag.NewFlagSet("serve", flag.ExitOnError)
	label := fs.String("label", "", "Optional relay label shown in status")
	_ = fs.Parse(args)

	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if err := client.Run(cfg, client.Options{
		Label:   *label,
		Browser: browserfetch.FromEnv(),
		Logger: func(format string, args ...any) {
			fmt.Printf(format+"\n", args...)
		},
	}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}

func runStatus(args []string) int {
	_ = args
	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if !cfg.Authenticated() {
		fmt.Println("Campus relay: auth missing")
		fmt.Println("Run `mdtero-relay login` or re-run the installer.")
		return 1
	}
	payload, err := client.FetchStatus(cfg)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if connected, _ := payload["connected"].(bool); connected {
		fmt.Println("Campus relay: connected")
		if label, ok := payload["label"].(string); ok && strings.TrimSpace(label) != "" {
			fmt.Println("Label:", label)
		}
		if outlet, ok := payload["outlet"].(map[string]any); ok {
			fmt.Printf("Outlet: %v / %v / %v\n", outlet["asn"], outlet["city"], outlet["ip"])
		}
		fmt.Println(payload["action_hint"])
		return 0
	}
	fmt.Println("Campus relay: offline")
	fmt.Println(payload["action_hint"])
	for _, command := range []string{"mdtero-relay install", "mdtero-relay serve"} {
		fmt.Println(" ", command)
	}
	return 1
}

func runLogin(args []string) int {
	fs := flag.NewFlagSet("login", flag.ExitOnError)
	apiKey := fs.String("api-key", "", "Mdtero API key")
	apiBase := fs.String("api-base", config.DefaultAPIBase, "Mdtero API base URL")
	label := fs.String("label", "", "Optional relay label")
	browser := fs.Bool("browser", true, "Open browser OAuth login when --api-key is not provided")
	timeout := fs.Duration("timeout", 3*time.Minute, "How long to wait for browser login")
	_ = fs.Parse(args)

	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if strings.TrimSpace(*apiBase) != "" {
		cfg.APIBaseURL = strings.TrimRight(strings.TrimSpace(*apiBase), "/")
	}
	if strings.TrimSpace(*label) != "" {
		cfg.Label = strings.TrimSpace(*label)
	}

	if strings.TrimSpace(*apiKey) != "" {
		cfg.APIKey = strings.TrimSpace(*apiKey)
	} else if *browser {
		result, err := auth.WebLogin(*timeout)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		cfg.APIKey = result.APIKey
		if result.Prefix != "" {
			fmt.Println("Saved API key prefix:", result.Prefix)
		}
	} else if !cfg.Authenticated() {
		fmt.Fprintln(os.Stderr, "Provide --api-key or use browser login (default).")
		return 2
	}

	if !cfg.Authenticated() {
		fmt.Fprintln(os.Stderr, "Mdtero API key is missing after login.")
		return 1
	}
	if err := config.Save(cfg); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	fmt.Println("Saved Mdtero relay credentials.")
	return 0
}

func runInstall(args []string) int {
	fs := flag.NewFlagSet("install", flag.ExitOnError)
	apiKey := fs.String("api-key", "", "Mdtero API key")
	apiBase := fs.String("api-base", config.DefaultAPIBase, "Mdtero API base URL")
	label := fs.String("label", "", "Optional relay label")
	_ = fs.Parse(args)

	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	if strings.TrimSpace(*apiKey) != "" {
		cfg.APIKey = strings.TrimSpace(*apiKey)
	}
	if strings.TrimSpace(*apiBase) != "" {
		cfg.APIBaseURL = strings.TrimRight(strings.TrimSpace(*apiBase), "/")
	}
	if strings.TrimSpace(*label) != "" {
		cfg.Label = strings.TrimSpace(*label)
	}
	if !cfg.Authenticated() {
		fmt.Println("Mdtero API key required.")
		fmt.Println("Get one at https://mdtero.com/settings/api-keys")
		fmt.Println("Then rerun: mdtero-relay install --api-key <key>")
		return 1
	}
	if err := config.Save(cfg); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}

	binaryPath, err := os.Executable()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	binaryPath, err = filepath.EvalSymlinks(binaryPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}

	manager := service.New()
	if err := manager.Install(binaryPath, "serve"); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	status, _ := manager.Status()
	fmt.Printf("Campus relay installed (%s).\n", status)
	fmt.Println("It will start automatically on login and reconnect in the background.")
	fmt.Println("Check status anytime with: mdtero-relay status")
	return 0
}

func runUninstall(args []string) int {
	_ = args
	if err := service.New().Uninstall(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	fmt.Println("Campus relay service removed.")
	return 0
}
