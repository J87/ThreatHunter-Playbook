# WMI Win32_Process Class and Create Method for Remote Execution

## Metadata


|               |    |
|:--------------|:---|
| id            | WIN-190810201010 |
| author        | Roberto Rodriguez @Cyb3rWard0g |
| creation date | 2019/08/10 |
| platform      | Windows |
| playbook link |  |
        

## Technical Description
WMI is the Microsoft implementation of the Web-Based Enterprise Management (WBEM) and Common Information Model (CIM).
Both standards aim to provide an industry-agnostic means of collecting and transmitting information related to any managed component in an enterprise.
An example of a managed component in WMI would be a running process, registry key, installed service, file information, etc.
At a high level, Microsoft’s implementation of these standards can be summarized as follows > Managed Components Managed components are represented as WMI objects — class instances representing highly structured operating system data. Microsoft provides a wealth of WMI objects that communicate information related to the operating system. E.g. Win32_Process, Win32_Service, AntiVirusProduct, Win32_StartupCommand, etc.

One well known lateral movement technique is performed via the WMI object — class Win32_Process and its method Create.
This is because the Create method allows a user to create a process either locally or remotely.
One thing to notice is that when the Create method is used on a remote system, the method is run under a host process named “Wmiprvse.exe”.

The process WmiprvSE.exe is what spawns the process defined in the CommandLine parameter of the Create method. Therefore, the new process created remotely will have Wmiprvse.exe as a parent. WmiprvSE.exe is a DCOM server and it is spawned underneath the DCOM service host svchost.exe with the following parameters C:\WINDOWS\system32\svchost.exe -k DcomLaunch -p.
From a logon session perspective, on the target, WmiprvSE.exe is spawned in a different logon session by the DCOM service host. However, whatever is executed by WmiprvSE.exe occurs on the new network type (3) logon session created by the user that authenticated from the network.

Additional Reading
* https://github.com/hunters-forge/ThreatHunter-Playbook/tree/master/docs/library/logon_session.md

## Hypothesis
Adversaries might be leveraging WMI Win32_Process class and method Create to execute code remotely across my environment

## Analytics

### Initialize Analytics Engine

from openhunt.mordorutils import *
spark = get_spark()

### Download & Process Mordor File

mordor_file = "https://raw.githubusercontent.com/hunters-forge/mordor/master/datasets/small/windows/execution/empire_invoke_wmi.tar.gz"
registerMordorSQLTable(spark, mordor_file, "mordorTable")

### Analytic I


| FP Rate  | Log Channel | Description   |
| :--------| :-----------| :-------------|
| Medium       | ['Security']          | Look for wmiprvse.exe spawning processes that are part of non-system account sessions.            |
            

df = spark.sql(
    '''
SELECT `@timestamp`, computer_name, SubjectUserName, TargetUserName, NewProcessName, CommandLine
FROM mordorTable
WHERE channel = "Security"
    AND event_id = 4688
    AND lower(ParentProcessName) LIKE "%wmiprvse.exe"
    AND NOT TargetLogonId = "0x3e7"
    '''
)
df.show(10,False)

### Analytic II


| FP Rate  | Log Channel | Description   |
| :--------| :-----------| :-------------|
| Medium       | ['Microsoft-Windows-Sysmon/Operational']          | Look for wmiprvse.exe spawning processes that are part of non-system account sessions.            |
            

df = spark.sql(
    '''
SELECT `@timestamp`, computer_name, User, Image, CommandLine
FROM mordorTable
WHERE channel = "Microsoft-Windows-Sysmon/Operational"
    AND event_id = 1
    AND lower(ParentImage) LIKE "%wmiprvse.exe"
    AND NOT LogonId = "0x3e7"
    '''
)
df.show(10,False)

### Analytic III


| FP Rate  | Log Channel | Description   |
| :--------| :-----------| :-------------|
| Low       | ['Security']          | Look for non-system accounts leveraging WMI over the netwotk to execute code            |
            

df = spark.sql(
    '''
SELECT o.`@timestamp`, o.computer_name, o.SubjectUserName, o.TargetUserName, o.NewProcessName, o.CommandLine, a.IpAddress
FROM mordorTable o
INNER JOIN (
    SELECT computer_name,TargetUserName,TargetLogonId,IpAddress
    FROM mordorTable
    WHERE channel = "Security"
        AND LogonType = 3
        AND IpAddress is not null
        AND NOT TargetUserName LIKE "%$"
    ) a
ON o.TargetLogonId = a.TargetLogonId
WHERE o.channel = "Security"
    AND o.event_id = 4688
    AND lower(o.ParentProcessName) LIKE "%wmiprvse.exe"
    AND NOT o.TargetLogonId = "0x3e7"
    '''
)
df.show(10,False)

## Detection Blindspots


## Hunter Notes
* Stack the child processes of wmiprvse.exe in your environment. This is very helpful to reduce the number of false positive and understand your environment. You can categorize the data returned by business unit.
* Look for wmiprvse.exe spawning new processes that are part of a network type logon session.
* Enrich events with Network Logon events (4624 - Logon Type 3)

## Hunt Output

| Category | Type | Name     |
| :--------| :----| :--------|
| signature | SIGMA | [sysmon_wmi_module_load](https://github.com/hunters-forge/ThreatHunter-Playbook/blob/master/signatures/sigma/sysmon_wmi_module_load.yml) |

## References
* https://posts.specterops.io/threat-hunting-with-jupyter-notebooks-part-4-sql-join-via-apache-sparksql-6630928c931e
* https://posts.specterops.io/real-time-sysmon-processing-via-ksql-and-helk-part-3-basic-use-case-8fbf383cb54f