package main

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
)

func mustEnv(cmd *exec.Cmd, extra map[string]string) {
	cmd.Env = os.Environ()
	for key, value := range extra {
		cmd.Env = append(cmd.Env, key+"="+value)
	}
}

// bundledNodeDir returns the directory holding node/npm inside a portable root,
// or "" when the package has none (older builds, or a dev run from source).
// Connector CLIs install from npm and are Node programs themselves, so the
// runtime has to be on PATH for the whole life of the server process.
func bundledNodeDir(root string) string {
	if runtime.GOOS == "windows" {
		if _, err := os.Stat(filepath.Join(root, "node", "node.exe")); err == nil {
			return filepath.Join(root, "node")
		}
		return ""
	}
	if _, err := os.Stat(filepath.Join(root, "node", "bin", "node")); err == nil {
		return filepath.Join(root, "node", "bin")
	}
	return ""
}

func startOctop(root string, port int) (*exec.Cmd, error) {
	py := pythonExe(root)
	launch := filepath.Join(root, "launch.py")
	cmd := exec.Command(py, launch, "run", "--host", "127.0.0.1", "--port", strconv.Itoa(port))
	cmd.Dir = root
	env := map[string]string{
		"OCTOP_HOME":           octopHome(),
		"OCTOP_GREEN_PACKAGES": filepath.Join(root, "packages"),
		"PYTHONNOUSERSITE":     "1",
		"PYTHONPATH":           "",
	}
	if nodeDir := bundledNodeDir(root); nodeDir != "" {
		env["OCTOP_BUNDLED_NODE"] = nodeDir
		env["PATH"] = nodeDir + string(os.PathListSeparator) + os.Getenv("PATH")
	}
	mustEnv(cmd, env)
	configureProcGroup(cmd)
	if runtime.GOOS == "linux" {
		// The Linux desktop release has no server terminal; the shell owns status
		// presentation just like the Windows GUI executable.
		cmd.Stdout = io.Discard
		cmd.Stderr = io.Discard
	} else if runtime.GOOS != "windows" {
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	}
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	return cmd, nil
}

func stopOctop(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	killProcessTree(cmd)
}

func dashboardURL(port int) string {
	return fmt.Sprintf("http://127.0.0.1:%d/", port)
}
