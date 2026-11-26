/* Upgrade existing deployments from the initial smallint port to the full TCP range. */
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id=OBJECT_ID(N'inkjet.PrinterMaster')
      AND name=N'TcpPort'
      AND TYPE_NAME(user_type_id)=N'smallint'
)
BEGIN
    ALTER TABLE inkjet.PrinterMaster ALTER COLUMN TcpPort int NOT NULL;
END;
GO
