# AUR package: `mlos-host-utils`

```sh
paru -S mlos-host-utils     # or yay, or makepkg -si
```

It builds from the tagged source tarball rather than shipping a prebuilt
binary, which is the normal AUR arrangement and costs about a second — the
agent is one Go package with no dependencies outside the standard library.

`PKGBUILD` here is a template: `__VERSION__` and `__SHA256__` are filled in
by `render.sh`, from the tarball GitHub actually serves for the tag.

```sh
./render.sh v0.1.3 build     # writes build/PKGBUILD and build/.SRCINFO
```

`.SRCINFO` is generated with `makepkg --printsrcinfo` rather than written by
hand, because the AUR reads it instead of the PKGBUILD and the two silently
disagreeing is the classic way to publish a package nobody can install.

## What the package does differently

Arch has `usbip` in its own repositories, so this is the one platform where
the agent never has to go and find a USB/IP client: it is a `depends`, and
pacman has already put it there. The package also ships the
`modules-load.d` fragment for `vhci-hcd`.

What it does *not* do is start anything. Installing the package gives you
the binary; the agent, the firewall rule and the pairing code still come
from one elevated run of:

```sh
sudo mlos-host-utils install
```

which notices it was installed by a package manager and leaves the binary
where pacman put it, rather than copying it to `/usr/local/bin` where
`pacman -Syu` would never update it again.

## Releasing

The `aur` job in `.github/workflows/host-utils.yml` runs on every `v*` tag:
it renders the recipe, *builds* it — the only place the PKGBUILD is ever
tested — and pushes to the AUR.

That last step needs an `AUR_SSH_KEY` repository secret: the private half of
an SSH key added to the AUR account under
[My Account → SSH Public Key](https://aur.archlinux.org/account/). Without
it the job still builds and attaches the recipe to the run, so a release is
never blocked on it.

The first push is the one that creates the package, and the AUR only accepts
it if the account is the maintainer. For a package that has never existed,
push once by hand:

```sh
git clone ssh://aur@aur.archlinux.org/mlos-host-utils.git
cp build/PKGBUILD build/.SRCINFO mlos-host-utils/
cd mlos-host-utils && git add -A && git commit -m 0.1.3 && git push
```

After that the job takes over.
