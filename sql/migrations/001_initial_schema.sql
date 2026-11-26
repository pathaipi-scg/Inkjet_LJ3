/* JET3 integration schema. SQL Server 2019; idempotent and non-destructive. */
IF SCHEMA_ID(N'inkjet') IS NULL EXEC(N'CREATE SCHEMA inkjet AUTHORIZATION dbo');
GO
IF OBJECT_ID(N'inkjet.PrinterMaster', N'U') IS NULL
BEGIN
    CREATE TABLE inkjet.PrinterMaster (
        PrinterId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_PrinterMaster PRIMARY KEY,
        PrinterCode nvarchar(64) NOT NULL CONSTRAINT UQ_PrinterMaster_Code UNIQUE,
        PrinterName nvarchar(128) NOT NULL,
        IpAddress varchar(45) NOT NULL,
        TcpPort int NOT NULL,
        IsEnabled bit NOT NULL CONSTRAINT DF_PrinterMaster_IsEnabled DEFAULT (1),
        CreatedAt datetime2(3) NOT NULL
    );
END;
GO
IF OBJECT_ID(N'inkjet.TransactionLog', N'U') IS NULL
BEGIN
    CREATE TABLE inkjet.TransactionLog (
        TransactionId uniqueidentifier NOT NULL CONSTRAINT PK_TransactionLog PRIMARY KEY,
        PrinterId int NOT NULL,
        StartedAt datetime2(3) NOT NULL,
        CompletedAt datetime2(3) NOT NULL,
        RequestedText nvarchar(256) NOT NULL,
        BaselineText nvarchar(256) NULL,
        ReadbackText nvarchar(256) NULL,
        Outcome varchar(32) NOT NULL,
        ErrorCategory varchar(48) NOT NULL,
        Message nvarchar(1000) NOT NULL,
        ElapsedMs decimal(14,3) NOT NULL,
        CONSTRAINT FK_TransactionLog_PrinterMaster FOREIGN KEY (PrinterId)
            REFERENCES inkjet.PrinterMaster(PrinterId)
    );
END;
GO
IF OBJECT_ID(N'inkjet.PrinterStatus', N'U') IS NULL
BEGIN
    CREATE TABLE inkjet.PrinterStatus (
        StatusId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PrinterStatus PRIMARY KEY,
        PrinterId int NOT NULL,
        TransactionId uniqueidentifier NULL,
        ObservedAt datetime2(3) NOT NULL,
        NozzleState int NULL,
        MachineState int NULL,
        PrinterError int NULL,
        Headcover int NULL,
        ActSpeed decimal(12,3) NULL,
        ExternActualSpeed decimal(12,3) NULL,
        ExternMaxSpeed decimal(12,3) NULL,
        Inputs bigint NULL,
        EncoderDirection int NULL,
        PrintGoHigh bit NULL,
        IsPrinting bit NULL,
        ExternTextReady bit NULL,
        ProductionStopped bit NULL,
        TriggersInhibited bit NULL,
        CommandEchoEnabled bit NULL,
        LoadedJob nvarchar(512) NULL,
        UnknownStatusFields nvarchar(max) NULL,
        CONSTRAINT FK_PrinterStatus_PrinterMaster FOREIGN KEY (PrinterId)
            REFERENCES inkjet.PrinterMaster(PrinterId),
        CONSTRAINT FK_PrinterStatus_TransactionLog FOREIGN KEY (TransactionId)
            REFERENCES inkjet.TransactionLog(TransactionId)
    );
END;
GO
IF OBJECT_ID(N'inkjet.StatusLog', N'U') IS NULL
BEGIN
    CREATE TABLE inkjet.StatusLog (
        StatusLogId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_StatusLog PRIMARY KEY,
        PrinterId int NOT NULL,
        TransactionId uniqueidentifier NULL,
        EventAt datetime2(3) NOT NULL,
        EventType varchar(32) NOT NULL,
        Severity varchar(16) NOT NULL,
        Message nvarchar(1000) NOT NULL,
        DataHex nvarchar(max) NULL,
        ElapsedMs decimal(14,3) NULL,
        CONSTRAINT FK_StatusLog_PrinterMaster FOREIGN KEY (PrinterId)
            REFERENCES inkjet.PrinterMaster(PrinterId),
        CONSTRAINT FK_StatusLog_TransactionLog FOREIGN KEY (TransactionId)
            REFERENCES inkjet.TransactionLog(TransactionId)
    );
END;
GO
IF OBJECT_ID(N'inkjet.ErrorLog', N'U') IS NULL
BEGIN
    CREATE TABLE inkjet.ErrorLog (
        ErrorId bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ErrorLog PRIMARY KEY,
        PrinterId int NOT NULL,
        TransactionId uniqueidentifier NULL,
        OccurredAt datetime2(3) NOT NULL,
        ErrorCategory varchar(48) NOT NULL,
        ErrorCode nvarchar(64) NULL,
        Message nvarchar(1000) NOT NULL,
        Details nvarchar(max) NULL,
        CONSTRAINT FK_ErrorLog_PrinterMaster FOREIGN KEY (PrinterId)
            REFERENCES inkjet.PrinterMaster(PrinterId),
        CONSTRAINT FK_ErrorLog_TransactionLog FOREIGN KEY (TransactionId)
            REFERENCES inkjet.TransactionLog(TransactionId)
    );
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'inkjet.PrinterStatus') AND name=N'IX_PrinterStatus_Latest')
    CREATE INDEX IX_PrinterStatus_Latest ON inkjet.PrinterStatus(PrinterId, ObservedAt DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'inkjet.TransactionLog') AND name=N'IX_TransactionLog_PrinterTime')
    CREATE INDEX IX_TransactionLog_PrinterTime ON inkjet.TransactionLog(PrinterId, StartedAt DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'inkjet.ErrorLog') AND name=N'IX_ErrorLog_PrinterTime')
    CREATE INDEX IX_ErrorLog_PrinterTime ON inkjet.ErrorLog(PrinterId, OccurredAt DESC);
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'inkjet.StatusLog') AND name=N'IX_StatusLog_Transaction')
    CREATE INDEX IX_StatusLog_Transaction ON inkjet.StatusLog(TransactionId, EventAt);
GO
CREATE OR ALTER VIEW inkjet.vw_PrinterStatus AS
WITH RankedStatus AS (
    SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.PrinterId ORDER BY s.ObservedAt DESC, s.StatusId DESC) AS RowNum
    FROM inkjet.PrinterStatus AS s
)
SELECT p.PrinterCode, p.PrinterName, p.IpAddress, p.TcpPort, p.IsEnabled,
       s.ObservedAt, s.NozzleState, s.MachineState, s.PrinterError, s.Headcover,
       s.ActSpeed, s.ExternActualSpeed, s.ExternMaxSpeed, s.Inputs,
       s.EncoderDirection, s.PrintGoHigh, s.IsPrinting, s.ExternTextReady,
    s.ProductionStopped, s.TriggersInhibited, s.CommandEchoEnabled,
    s.LoadedJob, s.UnknownStatusFields
FROM inkjet.PrinterMaster AS p
LEFT JOIN RankedStatus AS s ON s.PrinterId=p.PrinterId AND s.RowNum=1;
GO
CREATE OR ALTER VIEW inkjet.vw_TransactionHistory AS
SELECT t.TransactionId, p.PrinterCode, p.PrinterName, t.StartedAt, t.CompletedAt,
       t.RequestedText, t.BaselineText, t.ReadbackText, t.Outcome,
       t.ErrorCategory, t.Message, t.ElapsedMs
FROM inkjet.TransactionLog AS t
JOIN inkjet.PrinterMaster AS p ON p.PrinterId=t.PrinterId;
GO
CREATE OR ALTER VIEW inkjet.vw_ErrorHistory AS
SELECT e.ErrorId, e.TransactionId, p.PrinterCode, p.PrinterName, e.OccurredAt,
       e.ErrorCategory, e.ErrorCode, e.Message, e.Details
FROM inkjet.ErrorLog AS e
JOIN inkjet.PrinterMaster AS p ON p.PrinterId=e.PrinterId;
GO
CREATE OR ALTER VIEW inkjet.vw_DailySummary AS
SELECT p.PrinterCode, CONVERT(date, t.CompletedAt) AS SummaryDate,
       COUNT_BIG(*) AS TransactionCount,
       SUM(CASE WHEN t.Outcome='VERIFIED' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS VerifiedCount,
       SUM(CASE WHEN t.Outcome='MISMATCH' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS MismatchCount,
       SUM(CASE WHEN t.Outcome='FAILED' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS FailedCount,
       SUM(CASE WHEN t.Outcome='BLOCKED' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS BlockedCount
FROM inkjet.TransactionLog AS t
JOIN inkjet.PrinterMaster AS p ON p.PrinterId=t.PrinterId
WHERE t.Outcome <> 'STATUS_ONLY'
GROUP BY p.PrinterCode, CONVERT(date, t.CompletedAt);
GO
