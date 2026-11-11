/** Short warning labels for an active batch; shared by the batch row and the status strip. */
export interface WarningInput {
	reading?: { is_anomaly?: boolean; anomaly_reasons?: string[] | null; paired?: boolean } | null;
	tempStatus?: string;
}

export function batchWarnings({ reading, tempStatus }: WarningInput): string[] {
	const out: string[] = [];
	if (reading?.is_anomaly && (reading.anomaly_reasons?.length ?? 0) > 0) out.push('Anomaly');
	if (reading && reading.paired === false) out.push('Not logging');
	if (tempStatus === 'too_hot') out.push('Above yeast range');
	else if (tempStatus === 'too_cold') out.push('Below yeast range');
	return out;
}
