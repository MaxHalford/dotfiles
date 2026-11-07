{
  description = "Max Halford's dotfiles and NixOS hosts";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    hermes-agent.url = "github:NousResearch/hermes-agent/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19";
  };

  outputs =
    inputs@{
      nixpkgs,
      home-manager,
      hermes-agent,
      ...
    }:
    {
      nixosConfigurations.beelink-nixos = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        specialArgs = { inherit inputs; };
        modules = [
          ./nixos/beelink/configuration.nix
          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.extraSpecialArgs.hermesAgent = hermes-agent;
            home-manager.users.max = import ./nixos/beelink/home.nix;
          }
        ];
      };
    };
}
