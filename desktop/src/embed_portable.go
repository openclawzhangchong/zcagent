//go:build !production || darwin

package main

// Development builds look for zcagent-<plat>.zip or zcagent-portable-<plat>-*.zip
// beside the executable. macOS production copies the zip into Resources as
// zcagent-<plat>.zip.
var embeddedPortable []byte
