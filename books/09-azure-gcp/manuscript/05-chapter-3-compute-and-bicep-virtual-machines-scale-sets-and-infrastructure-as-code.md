# Chapter 3 - Compute and Bicep: Virtual Machines, Scale Sets, and Infrastructure as Code {#ch3}

## 3.1 Virtual Machines and Their Invisible Siblings

`az vm create` looks like `aws ec2 run-instances` and returns in ten seconds with a running machine - but it quietly created five resources, and knowing them is the difference between using Azure and fighting it. One command produces the **VM** itself, a **NIC**, a **managed disk**, a **public IP**, and a **network security group**, optionally attached to a brand-new VNet and subnet you never asked for (see the warning below). EC2 bundles the first four as attributes of the instance; Azure models each as a resource with its own lifecycle, which is more verbose and more flexible - you can swap a NIC, attach the same public IP to a load balancer, or delete the VM and keep the disks. The daily commands translate directly:

```bash
az vm create \
  -g rg-shopnow-dev -n shopnow-web-01 \
  --image Ubuntu2404 \
  --size Standard_B2s \
  --admin-username azureuser --generate-ssh-keys \
  --public-ip-sku Standard \
  --zone 1
```

Sizes read like instance families with different letters: **B-series** burstable (the `t3`/`t4g` analog, and the lab default), **D-series** general purpose (`m5`-class), **E-series** memory optimized (`r`-class), **F-series** compute bound. The `az vm list-sizes -l westeurope` page is the instance-type catalog, and the same region-availability caveat as AWS applies. Two deltas are genuinely better here: zones are explicit and stable - `--zone 1` is a real, documented placement - and the serial console and boot diagnostics are on by default, which turns a failed boot from a support ticket into a browser tab.

::: {.warn}
**Watch out - the implicit default network**

Run `az vm create` without `--vnet-name` and Azure silently builds a VNet, a subnet, and a public IP in the resource group. You get a working machine with a public address and a network nobody designed - the Azure equivalent of EC2-Classic-era habits, and the source of most "why is this VM internet-reachable?" findings. Every example in this book creates the network explicitly first ([Chapter 4](#ch4) builds the whole VNet story), and production Bicep never relies on implicit anything.
:::

## 3.2 Disks, Images, and the Boot Story

Managed disks come in Standard HDD, Standard SSD, Premium SSD, Premium SSD v2, and Ultra - a storage ladder that maps to EBS gp2/gp3/io2 with the same "most workloads want the mid tier" answer, and Premium SSD v2 is the price-performance successor worth defaulting to for anything stateful. Images come from the Marketplace, addressed by the four-part URN `Publisher:Offer:Sku:Version`; `az vm image list --output table` is the searchable catalog. There is no Amazon Linux here - Ubuntu LTS and Debian dominate the sample space, RHEL carries the enterprise story, and **Container-Optimized OS**-style minimalism is less of a theme because containers live on AKS in [Chapter 5](#ch5) rather than on plain VMs. Custom images and the image gallery (Azure Compute Gallery) fill the golden-AMI role when you get there.

## 3.3 Availability: Scale Sets and the HA Story

The **Virtual Machine Scale Set (VMSS)** is the Auto Scaling Group analog: a template-driven group of identical VMs with autoscale rules, rolling upgrades, and zone spread. Two deltas from the AWS chapter are pleasant. A single VMSS spans zones natively (`--zones 1 2 3`) with no placement-group gymnastics, and the **regional** VMSS option spreads across zones by default. The old **availability set** (fault/update domains) still exists for legacy parity; new designs use zones and stop there. Autoscale rules are metric-driven profiles configured on the VMSS itself, and the KEDA-driven scaling story returns properly in [Chapter 6](#ch6) and [Chapter 13](#ch13), where the same idea gets much simpler.

## 3.4 Bicep: Declarative Azure Without the JSON

Azure's control plane speaks **ARM templates** - JSON, verbose, machine-generated, the CloudFormation of this platform - and **Bicep** is the language everyone actually writes: a clean DSL that transpiles to ARM JSON, ships with the az CLI (`az bicep upgrade` keeps it current), and round-trips with it (`bicep build` compiles to JSON; `bicep decompile` reads CloudFormation-era handouts back). Where Terraform - the series' cross-cloud tool of record - builds a state file from the API's responses, Bicep leans on *deployment state*: the platform remembers what `az deployment` created, and `what-if` diffs the template against reality like `terraform plan`. For an Azure-only estate Bicep is the lower-ceremony choice; the capstone in [Chapter 15](#ch15) uses each where it fits and [Chapter 16](#ch16) gives the decision its full treatment.

The running example's web tier in Bicep - parameters, one NSG, one NIC, one VM - reads close to the mental model:

```bicep
param location string = resourceGroup().location
param adminUsername string
param sshPublicKey string
param vnetName string
param subnetName string

var subnetRef = resourceId('Microsoft.Network/virtualNetworks/subnets', vnetName, subnetName)

var nsgRules = [
  { name: 'ssh', priority: 100, port: 22 }
  { name: 'http', priority: 110, port: 80 }
]

resource nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: 'nsg-shopnow-web'
  location: location
  properties: {
    securityRules: [for rule in nsgRules: {
      name: rule.name
      properties: {
        priority: rule.priority
        direction: 'Inbound'
        access: 'Allow'
        protocol: 'Tcp'
        sourcePortRange: '*'
        destinationPortRange: string(rule.port)
        sourceAddressPrefix: '*'
        destinationAddressPrefix: '*'
      }
    }]
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2023-09-01' = {
  name: 'nic-shopnow-web-01'
  location: location
  properties: {
    networkSecurityGroup: { id: nsg.id }
    ipConfigurations: [ {
      name: 'ipconfig1'
      properties: {
        subnet: { id: subnetRef }   // defined in the network module
        privateIPAllocationMethod: 'Dynamic'
      }
    } ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: 'shopnow-web-01'
  location: location
  zones: [ '1' ]
  properties: {
    hardwareProfile: { vmSize: 'Standard_B2s' }
    osProfile: {
      computerName: 'shopnow-web-01'
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: { publicKeys: [ { path: '/home/${adminUsername}/.ssh/authorized_keys', keyData: sshPublicKey } ] }
      }
    }
    storageProfile: {
      imageReference: { publisher: 'Canonical', offer: 'ubuntu-24_04-lts', sku: 'server', version: 'latest' }
      osDisk: { createOption: 'FromImage', managedDisk: { storageAccountType: 'Premium_LRS' } }
    }
    networkProfile: { networkInterfaces: [ { id: nic.id } ] }
  }
}
```

Deploy it with the two commands every Bicep file shares - `az deployment group what-if` (the plan) and `az deployment group create` (the apply). **Modules** split the file along resource-group lines, and the **Azure Verified Modules** library supplies reviewed building blocks for the patterns you should not hand-roll.

## 3.5 Lab 1: A Bicep Stack You Can Break and Rebuild

::: {.lab}
### Lab 1 - Write, What-If, Deploy, Change, Destroy {#lab1}

1. Create the home for the stack: `az group create -n rg-shopnow-lab -l westeurope`.
2. Write `main.bicep` with the NSG, NIC, and VM from [Section 3.4](#ch3) (add a public IP and a simple cloud-init `customData` that installs nginx), plus `dev.bicepparam` supplying the admin username and your SSH key.
3. Preview honestly: `az deployment group what-if -g rg-shopnow-lab -f main.bicep -p dev.bicepparam` - read the `+`/`~` diff like a `terraform plan`.
4. Deploy: `az deployment group create -g rg-shopnow-lab -f main.bicep -p dev.bicepparam`, then `az vm open-port` is *not* needed - prove it - and `curl` the public IP for the nginx welcome page.
5. Change the template (bump the VM size to `Standard_B2ms`), run `what-if` again, and watch it predict exactly one resize - then apply it and verify with `az vm show -d`.
6. Break it on purpose: remove the http rule from the NSG, deploy, and lose the page; restore it and get the page back.
7. Destroy the whole experiment with one command - `az group delete -n rg-shopnow-lab -y` - and observe that nothing survived, which is the resource-group contract of [Chapter 1](#ch1) doing its job.
:::

::: {.note}
**Best practice - `what-if` is not drift detection**

`what-if` compares *template against live state*, but unlike Terraform it will not surface out-of-band console changes as reliably - deletions of unmanaged resources simply do not appear. Treat the template as the only door into the resource group (RBAC can enforce exactly that), and the comparison stays honest.
:::

**See also:** [Chapter 2](#ch2) explained the identity a deployment runs as, [Chapter 4](#ch4) replaces this chapter's single-subnet sketch with a network you would actually ship, and [Chapter 16](#ch16) closes the Bicep-versus-Terraform question for teams living on more than one cloud.
