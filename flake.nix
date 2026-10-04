{
  description = "rootme-sdk development environment";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  outputs = { nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
    in {
      devShells = nixpkgs.lib.genAttrs systems (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            packages = [ pkgs.python314 pkgs.uv pkgs.go-task pkgs.gh pkgs.ripgrep ];
            UV_PYTHON = pkgs.python314.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
            shellHook = ''
              export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
              export PATH="$PWD/.venv/bin:$PATH"
            '';
          };
        });
    };
}
