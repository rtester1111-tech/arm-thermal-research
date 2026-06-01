#!/usr/bin/env python3
import urllib.request
import json
import sys

def verify_gem5_resources():
    print("🔍 Fetching gem5 resources.json...")
    url = "https://resources.gem5.org/resources.json"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"❌ Failed to fetch resources.json: {e}")
        return

    resources_list = data.get('resources', [])
    print(f"✅ Downloaded resources.json. Total resources found: {len(resources_list)}")
    
    # We are looking for an arm64 linux kernel and ubuntu disk image
    arm64_kernels = []
    arm64_disks = []
    
    for res in resources_list:
        if res.get('architecture') == 'ARM':
            res_id = res.get('id', '')
            res_type = res.get('category', '')
            if res_type == 'kernel' and 'arm64' in res_id:
                arm64_kernels.append(res)
            elif res_type == 'disk image' and 'ubuntu' in res_id and 'arm64' in res_id:
                arm64_disks.append(res)
    
    print("\n[ Found ARM64 Linux Kernels ]")
    for k in arm64_kernels[:3]:
        print(f" - {k.get('id')}: {k.get('url')}")
        
    print("\n[ Found ARM64 Ubuntu Disk Images ]")
    for d in arm64_disks[:3]:
        print(f" - {d.get('id')}: {d.get('url')}")

    # Select the most appropriate ones
    best_kernel = arm64_kernels[0] if arm64_kernels else None
    best_disk = arm64_disks[0] if arm64_disks else None
    
    print("\n=======================================================")
    print(" 建議寫入 PHASE5_6_IMPLEMENTATION_PLAN.md 的替換連結：")
    print("=======================================================")
    if best_kernel:
        print(f"👉 Linux Kernel: {best_kernel.get('url')}")
    else:
        print("👉 Linux Kernel: 無法自動找到合適的 arm64 kernel，請手動確認。")
        
    if best_disk:
        print(f"👉 Disk Image: {best_disk.get('url')}")
    else:
        print("👉 Disk Image: 無法自動找到合適的 arm64 ubuntu image，請手動確認。")
    print("=======================================================\n")

if __name__ == "__main__":
    verify_gem5_resources()
