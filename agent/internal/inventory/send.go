package inventory

import (
	"context"

	pb "github.com/hlhelper/hl-agent/proto/fleet/v1"
	"google.golang.org/protobuf/types/known/timestamppb"
)

// BuildMessages collects current inventory + facts and returns up to three
// AgentToServer envelopes ready to send. Best-effort: any individual collector
// failure leaves that envelope nil (caller should nil-check).
//
// hostID is required so the server can route persistence.
// includeLang gates the language-package scan (off by default — opt-in).
// langRoots override the default search roots when non-empty.
func BuildMessages(ctx context.Context, hostID string, includeLang bool, langRoots []string) []*pb.AgentToServer {
	now := timestamppb.Now()
	out := make([]*pb.AgentToServer, 0, 3)

	// OS packages (+ optional language packages).
	pkgs, _ := CollectOSPackages()
	if includeLang {
		more, _ := CollectLangPackages(langRoots)
		pkgs = append(pkgs, more...)
	}
	if len(pkgs) > 0 {
		pi := &pb.PackageInventory{
			HostId:       hostID,
			At:           now,
			FullSnapshot: true,
		}
		for _, p := range pkgs {
			pi.Added = append(pi.Added, &pb.PackageInventory_Pkg{
				Ecosystem: p.Ecosystem,
				Name:      p.Name,
				Version:   p.Version,
				Source:    p.Source,
				Arch:      p.Arch,
			})
		}
		out = append(out, &pb.AgentToServer{
			Msg: &pb.AgentToServer_PackageInventory{PackageInventory: pi},
		})
	}

	// Containers.
	cts, _ := CollectContainers(ctx)
	if cts != nil {
		ci := &pb.ContainerInventory{
			HostId:       hostID,
			At:           now,
			FullSnapshot: true,
		}
		for _, c := range cts {
			ci.Containers = append(ci.Containers, &pb.ContainerInventory_Container{
				Id:          c.ID,
				Name:        c.Name,
				ImageRef:    c.ImageRef,
				ImageDigest: c.ImageDigest,
				State:       c.State,
				Engine:      c.Engine,
			})
		}
		out = append(out, &pb.AgentToServer{
			Msg: &pb.AgentToServer_ContainerInventory{ContainerInventory: ci},
		})
	}

	// Host facts.
	if f, err := CollectHostFacts(); err == nil {
		hf := &pb.HostFacts{
			HostId:  hostID,
			At:      now,
			Sshd:    f.SSHD,
			Sysctl:  f.Sysctl,
			Mounts:  f.Mounts,
			FsPerms: f.FsPerms,
		}
		out = append(out, &pb.AgentToServer{
			Msg: &pb.AgentToServer_HostFacts{HostFacts: hf},
		})
	}

	return out
}
