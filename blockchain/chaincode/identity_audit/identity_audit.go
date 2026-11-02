/*
 * AIORI - Identity Audit Chaincode for Hyperledger Fabric
 *
 * This chaincode manages tamper-evident audit records for device identity
 * events on a permissioned blockchain. Stored data is privacy-aware:
 * only pseudonymous profile IDs and fingerprint digests (hashes) are recorded.
 *
 * No raw packet payloads or personally identifiable information is stored.
 */

package main

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// IdentityAuditContract implements the chaincode interface.
type IdentityAuditContract struct {
	contractapi.Contract
}

// AuditRecord represents a single identity audit entry on the ledger.
type AuditRecord struct {
	RecordID         string `json:"record_id"`
	ProfileID        string `json:"profile_id"`
	IPv6Address      string `json:"ipv6_address,omitempty"`
	EventType        string `json:"event_type"`
	FingerprintDigest string `json:"fingerprint_digest,omitempty"`
	Timestamp        string `json:"timestamp"`
	TxID             string `json:"tx_id,omitempty"`
}

// InitLedger initializes the chaincode with seed data (optional).
func (c *IdentityAuditContract) InitLedger(ctx contractapi.TransactionContextInterface) error {
	fmt.Println("AIORI Identity Audit chaincode initialized.")
	return nil
}

// RecordIdentityLink creates an audit record for an identity-address association.
func (c *IdentityAuditContract) RecordIdentityLink(
	ctx contractapi.TransactionContextInterface,
	recordID string,
	profileID string,
	ipv6Address string,
	fingerprintDigest string,
) error {
	record := AuditRecord{
		RecordID:         recordID,
		ProfileID:        profileID,
		IPv6Address:      ipv6Address,
		EventType:        "identity_linked",
		FingerprintDigest: fingerprintDigest,
		Timestamp:        time.Now().UTC().Format(time.RFC3339),
		TxID:             ctx.GetStub().GetTxID(),
	}

	data, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal record: %v", err)
	}

	return ctx.GetStub().PutState(recordID, data)
}

// RecordProfileCreated creates an audit record for a new profile.
func (c *IdentityAuditContract) RecordProfileCreated(
	ctx contractapi.TransactionContextInterface,
	recordID string,
	profileID string,
	fingerprintDigest string,
) error {
	record := AuditRecord{
		RecordID:         recordID,
		ProfileID:        profileID,
		EventType:        "profile_created",
		FingerprintDigest: fingerprintDigest,
		Timestamp:        time.Now().UTC().Format(time.RFC3339),
		TxID:             ctx.GetStub().GetTxID(),
	}

	data, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal record: %v", err)
	}

	return ctx.GetStub().PutState(recordID, data)
}

// RecordAnomalyDetected creates an audit record for an anomaly detection event.
func (c *IdentityAuditContract) RecordAnomalyDetected(
	ctx contractapi.TransactionContextInterface,
	recordID string,
	profileID string,
	ipv6Address string,
	anomalySummary string,
) error {
	record := AuditRecord{
		RecordID:         recordID,
		ProfileID:        profileID,
		IPv6Address:      ipv6Address,
		EventType:        "anomaly_detected",
		FingerprintDigest: anomalySummary,
		Timestamp:        time.Now().UTC().Format(time.RFC3339),
		TxID:             ctx.GetStub().GetTxID(),
	}

	data, err := json.Marshal(record)
	if err != nil {
		return fmt.Errorf("failed to marshal record: %v", err)
	}

	return ctx.GetStub().PutState(recordID, data)
}

// QueryRecord retrieves a single audit record by ID.
func (c *IdentityAuditContract) QueryRecord(
	ctx contractapi.TransactionContextInterface,
	recordID string,
) (*AuditRecord, error) {
	data, err := ctx.GetStub().GetState(recordID)
	if err != nil {
		return nil, fmt.Errorf("failed to read from ledger: %v", err)
	}
	if data == nil {
		return nil, fmt.Errorf("record %s not found", recordID)
	}

	var record AuditRecord
	err = json.Unmarshal(data, &record)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal record: %v", err)
	}

	return &record, nil
}

// QueryHistoryByProfile retrieves all audit records for a profile using
// a rich query (requires CouchDB state database).
func (c *IdentityAuditContract) QueryHistoryByProfile(
	ctx contractapi.TransactionContextInterface,
	profileID string,
) ([]*AuditRecord, error) {
	queryString := fmt.Sprintf(
		`{"selector":{"profile_id":"%s"}}`,
		profileID,
	)

	resultsIterator, err := ctx.GetStub().GetQueryResult(queryString)
	if err != nil {
		return nil, fmt.Errorf("failed to execute query: %v", err)
	}
	defer resultsIterator.Close()

	var records []*AuditRecord
	for resultsIterator.HasNext() {
		queryResult, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		var record AuditRecord
		err = json.Unmarshal(queryResult.Value, &record)
		if err != nil {
			return nil, err
		}
		records = append(records, &record)
	}

	return records, nil
}

// VerifyRecord checks that a record exists on the ledger and returns it.
func (c *IdentityAuditContract) VerifyRecord(
	ctx contractapi.TransactionContextInterface,
	recordID string,
) (string, error) {
	data, err := ctx.GetStub().GetState(recordID)
	if err != nil {
		return "", fmt.Errorf("verification failed: %v", err)
	}
	if data == nil {
		return "", fmt.Errorf("record %s not found on ledger", recordID)
	}

	return string(data), nil
}

func main() {
	chaincode, err := contractapi.NewChaincode(&IdentityAuditContract{})
	if err != nil {
		fmt.Printf("Error creating AIORI chaincode: %v\n", err)
		return
	}

	if err := chaincode.Start(); err != nil {
		fmt.Printf("Error starting AIORI chaincode: %v\n", err)
	}
}
