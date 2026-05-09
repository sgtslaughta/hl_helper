---
title: Protocol Documentation
status: stable
---

# Protocol Documentation
<a name="top"></a>

## Table of Contents

- [fleet/v1/agent_bridge.proto](#fleet_v1_agent_bridge-proto)
    - [AgentToServer](#fleet-v1-AgentToServer)
    - [CapabilityRequest](#fleet-v1-CapabilityRequest)
    - [CertIssueResponse](#fleet-v1-CertIssueResponse)
    - [CertRotateRequest](#fleet-v1-CertRotateRequest)
    - [Decommission](#fleet-v1-Decommission)
    - [DecommissionAck](#fleet-v1-DecommissionAck)
    - [Heartbeat](#fleet-v1-Heartbeat)
    - [HeartbeatAck](#fleet-v1-HeartbeatAck)
    - [HostMetrics](#fleet-v1-HostMetrics)
    - [ManifestUpdate](#fleet-v1-ManifestUpdate)
    - [ResumeRequest](#fleet-v1-ResumeRequest)
    - [ServerToAgent](#fleet-v1-ServerToAgent)
  
    - [AgentBridge](#fleet-v1-AgentBridge)
  
- [fleet/v1/commands.proto](#fleet_v1_commands-proto)
    - [DockerOp](#fleet-v1-DockerOp)
    - [FileTransfer](#fleet-v1-FileTransfer)
    - [GetFacts](#fleet-v1-GetFacts)
    - [PkgUpdate](#fleet-v1-PkgUpdate)
    - [PluginInvoke](#fleet-v1-PluginInvoke)
    - [Reboot](#fleet-v1-Reboot)
    - [ShellExec](#fleet-v1-ShellExec)
    - [TerminalOpen](#fleet-v1-TerminalOpen)
  
    - [FileTransfer.Dir](#fleet-v1-FileTransfer-Dir)
  
- [fleet/v1/envelope.proto](#fleet_v1_envelope-proto)
    - [CapabilityToken](#fleet-v1-CapabilityToken)
    - [CommandEnvelope](#fleet-v1-CommandEnvelope)
  
    - [RiskLevel](#fleet-v1-RiskLevel)
  
- [fleet/v1/results.proto](#fleet_v1_results-proto)
    - [ResultEnvelope](#fleet-v1-ResultEnvelope)
  
    - [ResultStatus](#fleet-v1-ResultStatus)
  
- [Scalar Value Types](#scalar-value-types)



<a name="fleet_v1_agent_bridge-proto"></a>
<p align="right"><a href="#top">Top</a></p>

## fleet/v1/agent_bridge.proto



<a name="fleet-v1-AgentToServer"></a>

### AgentToServer



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| heartbeat | [Heartbeat](#fleet-v1-Heartbeat) |  |  |
| result | [ResultEnvelope](#fleet-v1-ResultEnvelope) |  |  |
| resume | [ResumeRequest](#fleet-v1-ResumeRequest) |  |  |
| cap_req | [CapabilityRequest](#fleet-v1-CapabilityRequest) |  |  |
| cert_rotate | [CertRotateRequest](#fleet-v1-CertRotateRequest) |  |  |
| decom_ack | [DecommissionAck](#fleet-v1-DecommissionAck) |  |  |






<a name="fleet-v1-CapabilityRequest"></a>

### CapabilityRequest



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| host_id | [string](#string) |  |  |
| scope | [string](#string) |  |  |






<a name="fleet-v1-CertIssueResponse"></a>

### CertIssueResponse



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| cert_chain_pem | [bytes](#bytes) |  |  |
| not_after | [google.protobuf.Timestamp](#google-protobuf-Timestamp) |  |  |






<a name="fleet-v1-CertRotateRequest"></a>

### CertRotateRequest



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| host_id | [string](#string) |  |  |
| csr_pem | [bytes](#bytes) |  |  |






<a name="fleet-v1-Decommission"></a>

### Decommission



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| reason | [string](#string) |  |  |
| requested_by | [string](#string) |  |  |






<a name="fleet-v1-DecommissionAck"></a>

### DecommissionAck



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| at | [google.protobuf.Timestamp](#google-protobuf-Timestamp) |  |  |






<a name="fleet-v1-Heartbeat"></a>

### Heartbeat



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| host_id | [string](#string) |  |  |
| at | [google.protobuf.Timestamp](#google-protobuf-Timestamp) |  |  |
| last_acked_seq | [uint64](#uint64) |  |  |
| metrics | [HostMetrics](#fleet-v1-HostMetrics) |  |  |
| agent_version | [string](#string) |  |  |
| signature | [bytes](#bytes) |  |  |






<a name="fleet-v1-HeartbeatAck"></a>

### HeartbeatAck



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| server_at | [google.protobuf.Timestamp](#google-protobuf-Timestamp) |  |  |
| next_expected_seq | [uint64](#uint64) |  |  |






<a name="fleet-v1-HostMetrics"></a>

### HostMetrics



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| load_1 | [float](#float) |  |  |
| load_5 | [float](#float) |  |  |
| load_15 | [float](#float) |  |  |
| mem_used_pct | [float](#float) |  |  |
| disk_used_pct | [float](#float) |  |  |
| uptime_seconds | [uint64](#uint64) |  |  |






<a name="fleet-v1-ManifestUpdate"></a>

### ManifestUpdate



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| manifest_signed | [bytes](#bytes) |  |  |






<a name="fleet-v1-ResumeRequest"></a>

### ResumeRequest



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| host_id | [string](#string) |  |  |
| stream_session_id | [string](#string) |  |  |
| last_seq | [uint64](#uint64) |  |  |






<a name="fleet-v1-ServerToAgent"></a>

### ServerToAgent



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| command | [CommandEnvelope](#fleet-v1-CommandEnvelope) |  |  |
| hb_ack | [HeartbeatAck](#fleet-v1-HeartbeatAck) |  |  |
| cert_issue | [CertIssueResponse](#fleet-v1-CertIssueResponse) |  |  |
| manifest | [ManifestUpdate](#fleet-v1-ManifestUpdate) |  |  |
| decom | [Decommission](#fleet-v1-Decommission) |  |  |





 

 

 


<a name="fleet-v1-AgentBridge"></a>

### AgentBridge


| Method Name | Request Type | Response Type | Description |
| ----------- | ------------ | ------------- | ------------|
| Stream | [AgentToServer](#fleet-v1-AgentToServer) stream | [ServerToAgent](#fleet-v1-ServerToAgent) stream |  |

 



<a name="fleet_v1_commands-proto"></a>
<p align="right"><a href="#top">Top</a></p>

## fleet/v1/commands.proto



<a name="fleet-v1-DockerOp"></a>

### DockerOp



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| op | [string](#string) |  |  |
| container | [string](#string) |  |  |






<a name="fleet-v1-FileTransfer"></a>

### FileTransfer



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| dir | [FileTransfer.Dir](#fleet-v1-FileTransfer-Dir) |  |  |
| remote_path | [string](#string) |  |  |
| size_bytes | [uint64](#uint64) |  |  |






<a name="fleet-v1-GetFacts"></a>

### GetFacts



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| keys | [string](#string) | repeated |  |






<a name="fleet-v1-PkgUpdate"></a>

### PkgUpdate



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| classes | [string](#string) | repeated |  |
| dry_run | [bool](#bool) |  |  |






<a name="fleet-v1-PluginInvoke"></a>

### PluginInvoke



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| plugin_id | [string](#string) |  |  |
| payload | [bytes](#bytes) |  |  |






<a name="fleet-v1-Reboot"></a>

### Reboot



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| delay_seconds | [uint32](#uint32) |  |  |
| reason | [string](#string) |  |  |






<a name="fleet-v1-ShellExec"></a>

### ShellExec



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| command | [string](#string) |  |  |
| args | [string](#string) | repeated |  |
| timeout_seconds | [uint32](#uint32) |  |  |






<a name="fleet-v1-TerminalOpen"></a>

### TerminalOpen



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| session_id | [string](#string) |  |  |
| cols | [uint32](#uint32) |  |  |
| rows | [uint32](#uint32) |  |  |





 


<a name="fleet-v1-FileTransfer-Dir"></a>

### FileTransfer.Dir


| Name | Number | Description |
| ---- | ------ | ----------- |
| UPLOAD | 0 |  |
| DOWNLOAD | 1 |  |


 

 

 



<a name="fleet_v1_envelope-proto"></a>
<p align="right"><a href="#top">Top</a></p>

## fleet/v1/envelope.proto



<a name="fleet-v1-CapabilityToken"></a>

### CapabilityToken



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| biscuit | [bytes](#bytes) |  |  |
| declared_scopes | [string](#string) | repeated |  |






<a name="fleet-v1-CommandEnvelope"></a>

### CommandEnvelope



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| command_id | [string](#string) |  |  |
| host_id | [string](#string) |  |  |
| sequence | [uint64](#uint64) |  |  |
| nonce | [bytes](#bytes) |  |  |
| issued_at | [google.protobuf.Timestamp](#google-protobuf-Timestamp) |  |  |
| expires_at | [google.protobuf.Timestamp](#google-protobuf-Timestamp) |  |  |
| issued_by | [string](#string) |  |  |
| risk | [RiskLevel](#fleet-v1-RiskLevel) |  |  |
| capability | [CapabilityToken](#fleet-v1-CapabilityToken) |  |  |
| pkg_update | [PkgUpdate](#fleet-v1-PkgUpdate) |  |  |
| reboot | [Reboot](#fleet-v1-Reboot) |  |  |
| shell_exec | [ShellExec](#fleet-v1-ShellExec) |  |  |
| terminal_open | [TerminalOpen](#fleet-v1-TerminalOpen) |  |  |
| file_transfer | [FileTransfer](#fleet-v1-FileTransfer) |  |  |
| docker_op | [DockerOp](#fleet-v1-DockerOp) |  |  |
| get_facts | [GetFacts](#fleet-v1-GetFacts) |  |  |
| plugin_invoke | [PluginInvoke](#fleet-v1-PluginInvoke) |  |  |
| signature | [bytes](#bytes) |  |  |





 


<a name="fleet-v1-RiskLevel"></a>

### RiskLevel


| Name | Number | Description |
| ---- | ------ | ----------- |
| RISK_LOW | 0 |  |
| RISK_MED | 1 |  |
| RISK_HIGH | 2 |  |


 

 

 



<a name="fleet_v1_results-proto"></a>
<p align="right"><a href="#top">Top</a></p>

## fleet/v1/results.proto



<a name="fleet-v1-ResultEnvelope"></a>

### ResultEnvelope



| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| command_id | [string](#string) |  |  |
| host_id | [string](#string) |  |  |
| sequence | [uint64](#uint64) |  |  |
| started_at | [google.protobuf.Timestamp](#google-protobuf-Timestamp) |  |  |
| completed_at | [google.protobuf.Timestamp](#google-protobuf-Timestamp) |  |  |
| exit_code | [int32](#int32) |  |  |
| stdout_chunk | [bytes](#bytes) |  |  |
| stderr_chunk | [bytes](#bytes) |  |  |
| final | [bool](#bool) |  |  |
| status | [ResultStatus](#fleet-v1-ResultStatus) |  |  |
| rejection_reason | [string](#string) |  |  |
| prev_result_hash | [bytes](#bytes) |  |  |
| signature | [bytes](#bytes) |  |  |





 


<a name="fleet-v1-ResultStatus"></a>

### ResultStatus


| Name | Number | Description |
| ---- | ------ | ----------- |
| RESULT_OK | 0 |  |
| RESULT_FAIL | 1 |  |
| RESULT_REJECTED | 2 |  |
| RESULT_TIMEOUT | 3 |  |
| RESULT_CAPABILITY_DENIED | 4 |  |


 

 

 



## Scalar Value Types

| .proto Type | Notes | C++ | Java | Python | Go | C# | PHP | Ruby |
| ----------- | ----- | --- | ---- | ------ | -- | -- | --- | ---- |
| <a name="double" /> double |  | double | double | float | float64 | double | float | Float |
| <a name="float" /> float |  | float | float | float | float32 | float | float | Float |
| <a name="int32" /> int32 | Uses variable-length encoding. Inefficient for encoding negative numbers – if your field is likely to have negative values, use sint32 instead. | int32 | int | int | int32 | int | integer | Bignum or Fixnum (as required) |
| <a name="int64" /> int64 | Uses variable-length encoding. Inefficient for encoding negative numbers – if your field is likely to have negative values, use sint64 instead. | int64 | long | int/long | int64 | long | integer/string | Bignum |
| <a name="uint32" /> uint32 | Uses variable-length encoding. | uint32 | int | int/long | uint32 | uint | integer | Bignum or Fixnum (as required) |
| <a name="uint64" /> uint64 | Uses variable-length encoding. | uint64 | long | int/long | uint64 | ulong | integer/string | Bignum or Fixnum (as required) |
| <a name="sint32" /> sint32 | Uses variable-length encoding. Signed int value. These more efficiently encode negative numbers than regular int32s. | int32 | int | int | int32 | int | integer | Bignum or Fixnum (as required) |
| <a name="sint64" /> sint64 | Uses variable-length encoding. Signed int value. These more efficiently encode negative numbers than regular int64s. | int64 | long | int/long | int64 | long | integer/string | Bignum |
| <a name="fixed32" /> fixed32 | Always four bytes. More efficient than uint32 if values are often greater than 2^28. | uint32 | int | int | uint32 | uint | integer | Bignum or Fixnum (as required) |
| <a name="fixed64" /> fixed64 | Always eight bytes. More efficient than uint64 if values are often greater than 2^56. | uint64 | long | int/long | uint64 | ulong | integer/string | Bignum |
| <a name="sfixed32" /> sfixed32 | Always four bytes. | int32 | int | int | int32 | int | integer | Bignum or Fixnum (as required) |
| <a name="sfixed64" /> sfixed64 | Always eight bytes. | int64 | long | int/long | int64 | long | integer/string | Bignum |
| <a name="bool" /> bool |  | bool | boolean | boolean | bool | bool | boolean | TrueClass/FalseClass |
| <a name="string" /> string | A string must always contain UTF-8 encoded or 7-bit ASCII text. | string | String | str/unicode | string | string | string | String (UTF-8) |
| <a name="bytes" /> bytes | May contain any arbitrary sequence of bytes. | string | ByteString | str | []byte | ByteString | string | String (ASCII-8BIT) |

