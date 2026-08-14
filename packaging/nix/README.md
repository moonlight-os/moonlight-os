# Nix packaging

Two files, for two audiences:

- **`package.nix`** — the derivation, ready to drop into nixpkgs as
  `pkgs/by-name/ml/mlos-host-utils/package.nix`.
- **`module.nix`** — the NixOS module, `services.mlos-host-utils`.

Both are reachable from the flake at the repository root, so they are usable
today, without waiting on a nixpkgs review:

```sh
nix run github:MopigamesYT/moonlight-os#mlos-host-utils -- pair
```

## On NixOS, use the module

`mlos-host-utils install` is the wrong command here. It installs a usbip
package with the system package manager, writes a unit into
`/etc/systemd/system` and edits the firewall — and a `nixos-rebuild switch`
takes back the parts NixOS considers its own. The binary knows it is on
NixOS and says so rather than doing half of it.

```nix
{
  inputs.moonlight-os.url = "github:MopigamesYT/moonlight-os";

  # in configuration.nix
  imports = [ inputs.moonlight-os.nixosModules.default ];

  services.mlos-host-utils = {
    enable = true;
    openFirewall = true;   # off by default; see below
  };
}
```

That loads `vhci-hcd`, runs the agent at boot with the right `usbip` on its
path, and keeps the pairing code in `/var/lib/mlos-host-utils`.

`MLOS_HOST_UTILS_DIR` is set system-wide as well as on the unit, deliberately:
the agent and the CLI have to read the same state directory, and if they do
not, `mlos-host-utils pair` mints a *second* token and prints a code the
running agent will reject — with nothing on screen to suggest why.

`openFirewall` defaults to false. Anything that can reach the port and has
the pairing code can attach USB devices from its own machine to this one, so
opening it is a decision rather than a default.

## Getting it into nixpkgs

This is the one target CI cannot publish to — it is a reviewed pull request
against someone else's repository. What CI does do, on every tag, is build
the derivation and print the exact bumped `package.nix` in the run summary.
Locally that is:

```sh
./update.sh v0.1.3          # rewrites version and hash, needs nix
```

The hash `fetchFromGitHub` wants is of the unpacked tree, not of a tarball,
so unlike the AUR and winget checksums it cannot be worked out with
`sha256sum` — it comes from `nix flake prefetch`.

Once the package is in the tree, `passthru.updateScript` lets nixpkgs' own
update bot do version bumps without anyone here doing anything.
