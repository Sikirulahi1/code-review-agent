from typing import Any, Mapping

def classify_findings(
    new_findings: list[dict[str, Any]],
    prior_findings: list[Mapping[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """
    Compares new findings against prior findings using their fingerprints.
    Returns a dictionary categorizing findings into 'new', 'persisted', and 'resolved'.
    """
    prior_map = {str(f.get("fingerprint")): f for f in prior_findings if f.get("fingerprint")}
    
    new_results = []
    persisted_results = []
    
    new_fingerprints = set()
    
    for finding in new_findings:
        fp = str(finding.get("fingerprint", ""))
        if not fp:
            continue
            
        new_fingerprints.add(fp)
        
        if fp in prior_map:
            finding["status"] = "persisted"
            # Retain the previous comment ID so we can thread/reply in GitHub later
            finding["github_comment_id"] = prior_map[fp].get("github_comment_id")
            persisted_results.append(finding)
        else:
            finding["status"] = "new"
            new_results.append(finding)
            
    resolved_results = []
    for fp, prior_finding in prior_map.items():
        if fp not in new_fingerprints and prior_finding.get("status") != "resolved":
            # Issue was present before, but is not in the new findings. It got fixed!
            resolved = dict(prior_finding)
            resolved["status"] = "resolved"
            resolved_results.append(resolved)
            
    return {
        "new": new_results,
        "persisted": persisted_results,
        "resolved": resolved_results
    }
