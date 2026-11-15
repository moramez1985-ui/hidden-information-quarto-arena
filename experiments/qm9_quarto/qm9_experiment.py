from __future__ import annotations

import hashlib
import itertools
import json
import math
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from rdkit import Chem, rdBase
from rdkit.Chem import rdMolDescriptors


EXPERIMENT_DIR = Path(__file__).resolve().parent
ARCHIVE_PATH = EXPERIMENT_DIR / "dsgdb9nsd.xyz.tar.bz2"
ARCHIVE_URL = "https://ndownloader.figshare.com/files/3195389"
SAMPLE_COUNT = 1_024
SAMPLE_SIZE = 16
PUBLIC_SAMPLE_SEED = 20_261_108
PLAYERS = ("player_1", "player_2")

FEATURES: tuple[dict[str, Any], ...] = (
    {
        "feature_id": "contains_carbon",
        "name": "Contains carbon",
        "family": "composition",
        "definition": "At least one carbon atom occurs in the molecular formula.",
        "graph_predicate": "[#6]",
        "derivation": "RDKit atom identity in the sanitized source-SMILES graph.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Every QM9 entity contains carbon by domain construction.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_hydrogen",
        "name": "Contains hydrogen",
        "family": "composition",
        "definition": "The molecular formula contains at least one hydrogen atom, including implicit hydrogens.",
        "graph_predicate": "CalcMolFormula(mol) has H count > 0; explicit hydrogen graph nodes are counted separately in the manifest.",
        "derivation": "RDKit molecular formula from sanitized source-SMILES graph.",
        "hydrogen_semantics": "Includes implicit and explicit hydrogen atoms; distinct manifest fields preserve explicit-node and implicit-count values.",
        "dependencies": "Constant in the QM9 population.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_nitrogen",
        "name": "Contains nitrogen",
        "family": "composition",
        "definition": "At least one nitrogen atom occurs in the molecular graph.",
        "graph_predicate": "[#7]",
        "derivation": "RDKit atom identity in the sanitized source-SMILES graph.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_heteroatom by definition.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_oxygen",
        "name": "Contains oxygen",
        "family": "composition",
        "definition": "At least one oxygen atom occurs in the molecular graph.",
        "graph_predicate": "[#8]",
        "derivation": "RDKit atom identity in the sanitized source-SMILES graph.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_heteroatom by definition.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_fluorine",
        "name": "Contains fluorine",
        "family": "composition",
        "definition": "At least one fluorine atom occurs in the molecular graph.",
        "graph_predicate": "[#9]",
        "derivation": "RDKit atom identity in the sanitized source-SMILES graph.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Within QM9, halogen presence is fluorine presence; implies contains_heteroatom.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_heteroatom",
        "name": "Contains heteroatom",
        "family": "composition",
        "definition": "At least one atom other than carbon or hydrogen occurs in the molecular graph.",
        "graph_predicate": "Any atom with atomic number outside {1, 6}.",
        "derivation": "RDKit atom identities in the sanitized source-SMILES graph.",
        "hydrogen_semantics": "Hydrogen is excluded whether explicit or implicit.",
        "dependencies": "In QM9 this is exactly the union of nitrogen, oxygen, and fluorine presence.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_ring",
        "name": "Contains a ring",
        "family": "topology",
        "definition": "At least one atom belongs to a cycle in the sanitized molecular graph.",
        "graph_predicate": "[R]",
        "derivation": "RDKit ring-membership query after aromaticity and sanitization.",
        "hydrogen_semantics": "Hydrogens do not determine ring membership.",
        "dependencies": "Aromatic ring implies ring; implication does not make predicates equivalent.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_aromatic_ring",
        "name": "Contains an aromatic ring",
        "family": "topology",
        "definition": "At least one aromatic atom belongs to a ring in the sanitized molecular graph.",
        "graph_predicate": "[a;R]",
        "derivation": "RDKit aromaticity model and ring-membership perception.",
        "hydrogen_semantics": "Hydrogens do not determine aromaticity.",
        "dependencies": "Chemically implies contains_ring under the stated graph semantics.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_double_bond",
        "name": "Contains a double bond",
        "family": "bonding",
        "definition": "At least one sanitized graph bond has RDKit bond order 2.0.",
        "graph_predicate": "[*]=[*]",
        "derivation": "RDKit bond-order query; aromatic bonds are not counted as double bonds.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_multiple_bond by definition.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_triple_bond",
        "name": "Contains a triple bond",
        "family": "bonding",
        "definition": "At least one sanitized graph bond has RDKit bond order 3.0.",
        "graph_predicate": "[*]#[*]",
        "derivation": "RDKit bond-order query.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_multiple_bond by definition.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_multiple_bond",
        "name": "Contains a multiple bond",
        "family": "bonding",
        "definition": "At least one sanitized graph bond has bond order greater than 1.0; aromatic bonds are excluded.",
        "graph_predicate": "Any non-aromatic bond with RDKit bond order > 1.0.",
        "derivation": "RDKit bond types in the sanitized source-SMILES graph.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Contains_double_bond and contains_triple_bond each imply this feature.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_carbonyl",
        "name": "Contains a carbonyl",
        "family": "functional_group",
        "definition": "A carbon atom is double-bonded to an oxygen atom.",
        "graph_predicate": "[#6]=[#8]",
        "derivation": "RDKit SMARTS substructure match.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_oxygen and contains_double_bond.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_hydroxyl",
        "name": "Contains a hydroxyl group",
        "family": "functional_group",
        "definition": "An oxygen atom has one hydrogen and is single-bonded to carbon; this excludes water-like O-H groups.",
        "graph_predicate": "[#6]-[O;H1]",
        "derivation": "RDKit SMARTS with hydrogen count evaluated on a sanitized graph.",
        "hydrogen_semantics": "H1 includes implicit or explicit attached hydrogen as interpreted by RDKit SMARTS.",
        "dependencies": "Implies contains_oxygen and contains_hydrogen.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_nitrile",
        "name": "Contains a nitrile",
        "family": "functional_group",
        "definition": "A carbon atom is triple-bonded to a nitrogen atom.",
        "graph_predicate": "[#6]#[#7]",
        "derivation": "RDKit SMARTS substructure match.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_nitrogen and contains_triple_bond.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_amine",
        "name": "Contains an amine center",
        "family": "functional_group",
        "definition": "A neutral, trivalent nitrogen atom not directly bonded to a carbonyl carbon; excludes amide nitrogen and nitrile nitrogen.",
        "graph_predicate": "[N;X3;!$(N-C=O)]",
        "derivation": "RDKit SMARTS; includes primary, secondary, and tertiary amine centers meeting the predicate.",
        "hydrogen_semantics": "Hydrogen counts are not used; valence and graph neighborhood define the center.",
        "dependencies": "Implies contains_nitrogen; does not claim that every amine-like chemical class is covered.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_amide",
        "name": "Contains an amide",
        "family": "functional_group",
        "definition": "A nitrogen is single-bonded to a carbonyl carbon.",
        "graph_predicate": "[#7]-[#6](=[#8])",
        "derivation": "RDKit SMARTS substructure match.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_nitrogen, contains_carbonyl, and contains_oxygen.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_ester",
        "name": "Contains an ester",
        "family": "functional_group",
        "definition": "A carbonyl carbon is single-bonded to an oxygen which is single-bonded to carbon.",
        "graph_predicate": "[#6](=[#8])-[O;X2]-[#6]",
        "derivation": "RDKit SMARTS substructure match.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_carbonyl and contains_oxygen.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_carboxylic_acid",
        "name": "Contains a carboxylic acid",
        "family": "functional_group",
        "definition": "A carbonyl carbon is bonded to a hydroxyl oxygen.",
        "graph_predicate": "[#6](=[#8])-[O;H1]",
        "derivation": "RDKit SMARTS substructure match.",
        "hydrogen_semantics": "The hydroxyl oxygen may carry an implicit or explicit hydrogen.",
        "dependencies": "Implies contains_carbonyl, contains_oxygen, and contains_hydrogen.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "contains_saturated_ether_link",
        "name": "Contains a saturated ether linkage",
        "family": "functional_group",
        "definition": "An oxygen with two single bonds links two tetrahedral carbon atoms (C(sp3)-O-C(sp3)); esters are excluded by construction.",
        "graph_predicate": "[C;X4]-[O;X2]-[C;X4]",
        "derivation": "RDKit SMARTS substructure match.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "Implies contains_oxygen; this narrow predicate is not a definition of every ether class.",
        "scientifically_valid": True,
    },
    {
        "feature_id": "formal_charge_nonzero",
        "name": "Has nonzero formal charge",
        "family": "electronic_structure",
        "definition": "The sum of RDKit formal charges over all atoms is nonzero.",
        "graph_predicate": "sum(atom.GetFormalCharge()) != 0.",
        "derivation": "Formal charge encoded in the source SMILES and sanitized graph.",
        "hydrogen_semantics": "Not applicable.",
        "dependencies": "QM9 records are conventionally neutral; observed variance is measured, not assumed.",
        "scientifically_valid": True,
    },
)

SMARTS = {
    feature["feature_id"]: Chem.MolFromSmarts(feature["graph_predicate"])
    for feature in FEATURES
    if feature["graph_predicate"].startswith("[")
}
for feature_id, pattern in SMARTS.items():
    if pattern is None:
        raise RuntimeError(f"Invalid SMARTS for {feature_id}")


def _read_record(member_name: str, raw: bytes) -> dict[str, Any]:
    lines = raw.decode("utf-8", "strict").splitlines()
    if len(lines) < 3:
        raise ValueError("record has too few lines")
    atom_count = int(lines[0].strip())
    if atom_count <= 0 or len(lines) < atom_count + 5:
        raise ValueError("record atom count or record length is invalid")
    atom_rows = [line.split() for line in lines[2 : 2 + atom_count]]
    if len(atom_rows) != atom_count or any(len(row) < 4 for row in atom_rows):
        raise ValueError("record does not contain the declared number of atom rows")
    symbols = [row[0] for row in atom_rows]
    source_smiles_fields = lines[atom_count + 3].split()
    source_inchi_fields = lines[atom_count + 4].split()
    if not source_smiles_fields or not source_inchi_fields:
        raise ValueError("source SMILES or InChI field is empty")
    source_smiles = source_smiles_fields[0]
    source_inchi = source_inchi_fields[0]
    with rdBase.BlockLogs():
        mol = Chem.MolFromSmiles(source_smiles, sanitize=True)
    if mol is None:
        raise ValueError("RDKit failed to parse or sanitize source SMILES")
    if any(symbol not in {"C", "H", "N", "O", "F"} for symbol in symbols):
        raise ValueError("source XYZ contains an element outside the QM9 C/H/N/O/F domain")
    graph_element_counts = Counter(Chem.GetPeriodicTable().GetElementSymbol(atom.GetAtomicNum()) for atom in mol.GetAtoms())
    graph_element_counts["H"] += sum(atom.GetTotalNumHs() for atom in mol.GetAtoms())
    if graph_element_counts != Counter(symbols):
        raise ValueError("source XYZ elemental composition does not match the source SMILES formula")
    canonical_isomeric_smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    formula = rdMolDescriptors.CalcMolFormula(mol)
    explicit_hydrogen_nodes = sum(atom.GetAtomicNum() == 1 for atom in mol.GetAtoms())
    implicit_hydrogen_count = sum(atom.GetNumImplicitHs() for atom in mol.GetAtoms())
    total_hydrogen_count = sum(atom.GetTotalNumHs() for atom in mol.GetAtoms()) + explicit_hydrogen_nodes
    feature_values: dict[str, bool] = {}
    for feature in FEATURES:
        feature_id = feature["feature_id"]
        if feature_id == "contains_carbon":
            value = any(atom.GetAtomicNum() == 6 for atom in mol.GetAtoms())
        elif feature_id == "contains_hydrogen":
            value = total_hydrogen_count > 0
        elif feature_id == "contains_nitrogen":
            value = any(atom.GetAtomicNum() == 7 for atom in mol.GetAtoms())
        elif feature_id == "contains_oxygen":
            value = any(atom.GetAtomicNum() == 8 for atom in mol.GetAtoms())
        elif feature_id == "contains_fluorine":
            value = any(atom.GetAtomicNum() == 9 for atom in mol.GetAtoms())
        elif feature_id == "contains_heteroatom":
            value = any(atom.GetAtomicNum() not in (1, 6) for atom in mol.GetAtoms())
        elif feature_id == "contains_multiple_bond":
            value = any(
                not bond.GetIsAromatic() and bond.GetBondTypeAsDouble() > 1.0
                for bond in mol.GetBonds()
            )
        elif feature_id == "formal_charge_nonzero":
            value = sum(atom.GetFormalCharge() for atom in mol.GetAtoms()) != 0
        else:
            value = mol.HasSubstructMatch(SMARTS[feature_id])
        feature_values[feature_id] = bool(value)
    source_id = Path(member_name).stem
    return {
        "source_id": source_id,
        "original_smiles": source_smiles,
        "original_inchi": source_inchi,
        "canonical_isomeric_smiles": canonical_isomeric_smiles,
        "canonical_smiles": Chem.MolToSmiles(mol, canonical=True, isomericSmiles=False),
        "molecular_formula": formula,
        "atom_count_in_xyz": atom_count,
        "heavy_atom_count": sum(symbol != "H" for symbol in symbols),
        "formal_charge": sum(atom.GetFormalCharge() for atom in mol.GetAtoms()),
        "explicit_hydrogen_graph_nodes": explicit_hydrogen_nodes,
        "implicit_hydrogen_count": implicit_hydrogen_count,
        "total_hydrogen_count": total_hydrogen_count,
        "parse_status": "parsed_and_sanitized",
        **feature_values,
    }


def _validate_smarts_semantics() -> None:
    examples = {
        "contains_ring": ("C1CC1", "CCC"),
        "contains_aromatic_ring": ("c1ccccc1", "C1CCCCC1"),
        "contains_double_bond": ("C=C", "CC"),
        "contains_triple_bond": ("C#N", "C=N"),
        "contains_carbonyl": ("CC=O", "CCO"),
        "contains_hydroxyl": ("CCO", "COC"),
        "contains_nitrile": ("CC#N", "CC=N"),
        "contains_amine": ("CN", "CC(=O)N"),
        "contains_amide": ("CC(=O)N", "CN"),
        "contains_ester": ("CC(=O)OC", "CC(=O)O"),
        "contains_carboxylic_acid": ("CC(=O)O", "CC(=O)OC"),
        "contains_saturated_ether_link": ("COC", "CC(=O)OC"),
    }
    for feature_id, (positive_smiles, negative_smiles) in examples.items():
        pattern = SMARTS[feature_id]
        positive = Chem.MolFromSmiles(positive_smiles)
        negative = Chem.MolFromSmiles(negative_smiles)
        if positive is None or negative is None:
            raise AssertionError(f"Invalid SMARTS test molecule for {feature_id}")
        if not positive.HasSubstructMatch(pattern):
            raise AssertionError(f"SMARTS positive case failed for {feature_id}")
        if negative.HasSubstructMatch(pattern):
            raise AssertionError(f"SMARTS negative case failed for {feature_id}")


def _source_records() -> tuple[list[dict[str, Any]], list[dict[str, str]], int]:
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    archive_record_count = 0
    if not ARCHIVE_PATH.is_file():
        raise FileNotFoundError(f"Original QM9 archive not found at {ARCHIVE_PATH}")
    with tarfile.open(ARCHIVE_PATH, mode="r|bz2") as archive:
        for member in archive:
            if not member.isfile() or not member.name.endswith(".xyz"):
                continue
            archive_record_count += 1
            stream = archive.extractfile(member)
            if stream is None:
                failures.append({"source_id": Path(member.name).stem, "reason": "archive member could not be read"})
                continue
            raw_record = stream.read()
            try:
                records.append(_read_record(member.name, raw_record))
            except (UnicodeDecodeError, ValueError, IndexError) as error:
                lines = raw_record.decode("utf-8", "replace").splitlines()
                try:
                    atom_count = int(lines[0].strip())
                    smiles_fields = lines[atom_count + 3].split()
                    inchi_fields = lines[atom_count + 4].split()
                except (ValueError, IndexError):
                    smiles_fields = []
                    inchi_fields = []
                failures.append(
                    {
                        "source_id": Path(member.name).stem,
                        "reason": str(error),
                        "original_smiles": smiles_fields[0] if smiles_fields else None,
                        "alternate_smiles": smiles_fields[1] if len(smiles_fields) > 1 else None,
                        "original_inchi": inchi_fields[0] if inchi_fields else None,
                        "alternate_inchi": inchi_fields[1] if len(inchi_fields) > 1 else None,
                    }
                )
    return records, failures, archive_record_count


def _feature_relationships(matrix: pd.DataFrame, registry: pd.DataFrame) -> dict[str, Any]:
    ids = registry["feature_id"].tolist()
    exact_semantic = []
    semantic_keys: dict[str, list[str]] = defaultdict(list)
    for item in FEATURES:
        semantic_keys[item["graph_predicate"]].append(item["feature_id"])
    for predicate, group in semantic_keys.items():
        if len(group) > 1:
            exact_semantic.append({"predicate": predicate, "feature_ids": group})

    exact_dataset: list[dict[str, str]] = []
    complements: list[dict[str, str]] = []
    implications: list[dict[str, Any]] = []
    associations: list[dict[str, Any]] = []
    boolean = matrix[ids].astype(bool)
    for index, feature_a in enumerate(ids):
        a = boolean[feature_a].to_numpy(dtype=bool)
        for feature_b in ids[index + 1 :]:
            b = boolean[feature_b].to_numpy(dtype=bool)
            if np.array_equal(a, b):
                exact_dataset.append({"feature_a": feature_a, "feature_b": feature_b})
            if np.array_equal(a, ~b):
                complements.append({"feature_a": feature_a, "feature_b": feature_b})
            phi = (
                float(np.corrcoef(a.astype(np.float64), b.astype(np.float64))[0, 1])
                if a.any() and b.any() and not a.all() and not b.all()
                else None
            )
            ab = bool(np.all(~a | b))
            ba = bool(np.all(~b | a))
            if ab and a.any():
                implications.append(
                    {
                        "source": feature_a,
                        "target": feature_b,
                        "scope": "empirically_observed_in_full_QM9",
                        "source_true_count": int(a.sum()),
                        "target_true_count": int(b.sum()),
                        "correlation_phi": phi,
                        "equivalence": False,
                    }
                )
            if ba and b.any():
                implications.append(
                    {
                        "source": feature_b,
                        "target": feature_a,
                        "scope": "empirically_observed_in_full_QM9",
                        "source_true_count": int(b.sum()),
                        "target_true_count": int(a.sum()),
                        "correlation_phi": phi,
                        "equivalence": False,
                    }
                )
            if phi is not None:
                associations.append(
                    {
                        "feature_a": feature_a,
                        "feature_b": feature_b,
                        "phi": phi,
                        "exact_duplicate": np.array_equal(a, b),
                        "complement": np.array_equal(a, ~b),
                        "implication": ab or ba,
                    }
                )
    chemically_guaranteed = [
        ("contains_aromatic_ring", "contains_ring", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_nitrogen", "contains_heteroatom", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_oxygen", "contains_heteroatom", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_fluorine", "contains_heteroatom", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_carbonyl", "contains_oxygen", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_carbonyl", "contains_double_bond", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_nitrile", "contains_nitrogen", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_nitrile", "contains_triple_bond", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_amide", "contains_nitrogen", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_amide", "contains_carbonyl", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_ester", "contains_carbonyl", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_carboxylic_acid", "contains_carbonyl", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_saturated_ether_link", "contains_oxygen", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_hydroxyl", "contains_oxygen", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_hydroxyl", "contains_hydrogen", "chemically_guaranteed_by_graph_predicate_definitions"),
        ("contains_amine", "contains_nitrogen", "chemically_guaranteed_by_graph_predicate_definitions"),
    ]
    return {
        "exact_semantic_duplicates": exact_semantic,
        "dataset_exact_duplicates": exact_dataset,
        "dataset_complements": complements,
        "definition_guaranteed_implications": [
            {"source": source, "target": target, "scope": scope, "equivalence": False}
            for source, target, scope in chemically_guaranteed
        ],
        "qm9_domain_identities": [
            {
                "expression": "contains_heteroatom = contains_nitrogen OR contains_oxygen OR contains_fluorine",
                "scope": "guaranteed_only_under_QM9_C_H_N_O_F_domain_restriction",
                "equivalence_type": "domain-level identity, not feature identity collapse",
            }
        ],
        "full_dataset_implications": implications,
        "pairwise_phi_associations": associations,
    }


def _classify_feature_columns(
    matrix: pd.DataFrame, feature_ids: list[str]
) -> tuple[dict[str, str], dict[str, str]]:
    exact_classes: dict[bytes, str] = {}
    complement_classes: dict[bytes, str] = {}
    exact_rep: dict[str, str] = {}
    complement_rep: dict[str, str] = {}
    for feature_id in feature_ids:
        values = np.packbits(matrix[feature_id].to_numpy(dtype=np.uint8)).tobytes()
        inverse = np.packbits((~matrix[feature_id].to_numpy(dtype=bool)).astype(np.uint8)).tobytes()
        exact_rep[feature_id] = exact_classes.setdefault(values, feature_id)
        key = min(values, inverse)
        complement_rep[feature_id] = complement_classes.setdefault(key, feature_id)
    return exact_rep, complement_rep


def _canonical_game_structure(signature_by_entity: np.ndarray) -> tuple[int, ...]:
    """Canonicalize one valid mapping under bit permutations and independent bit flips."""
    best: tuple[int, ...] | None = None
    for permutation in itertools.permutations(range(4)):
        permuted = np.zeros(16, dtype=np.uint8)
        for output_bit, input_bit in enumerate(permutation):
            permuted |= ((signature_by_entity >> input_bit) & 1).astype(np.uint8) << output_bit
        for complement_mask in range(16):
            candidate = tuple(int(value ^ complement_mask) for value in permuted)
            if best is None or candidate < best:
                best = candidate
    assert best is not None
    return best


def _validate_quartet_accounting() -> None:
    feature_ids = [
        "contains_nitrogen",
        "contains_oxygen",
        "contains_fluorine",
        "contains_ring",
    ]
    signatures = np.arange(16, dtype=np.uint8)
    sample = pd.DataFrame(
        {
            feature_id: ((signatures >> bit) & 1).astype(bool)
            for bit, feature_id in enumerate(feature_ids)
        }
    )
    combinations = np.asarray([[0, 1, 2, 3]], dtype=np.int16)
    semantic_reps = {feature_id: feature_id for feature_id in feature_ids}
    exact_reps = {feature_id: feature_id for feature_id in feature_ids}
    complement_reps = {feature_id: feature_id for feature_id in feature_ids}
    valid = _quartets_for_sample(
        sample,
        combinations,
        feature_ids,
        semantic_reps,
        exact_reps,
        complement_reps,
        set(),
    )
    if valid["raw_valid_semantic_quartets"] != 1 or valid["game_structurally_distinct_valid_quartets"] != 1:
        raise AssertionError("A complete four-bit signature bijection was not accepted.")
    if _canonical_game_structure(signatures) != _canonical_game_structure(signatures ^ np.uint8(0b1010)):
        raise AssertionError("Global bit complementation did not preserve structural equivalence.")

    implication_sample = sample.copy()
    implication_sample[feature_ids[1]] = (
        implication_sample[feature_ids[0]].astype(np.uint8)
        | implication_sample[feature_ids[1]].astype(np.uint8)
    ).astype(bool)
    invalid = _quartets_for_sample(
        implication_sample,
        combinations,
        feature_ids,
        semantic_reps,
        exact_reps,
        complement_reps,
        {frozenset((feature_ids[0], feature_ids[1]))},
    )
    if invalid["raw_valid_semantic_quartets"] != 0:
        raise AssertionError("A quartet constrained by an implication was incorrectly accepted.")
    if invalid["invalid_rejected_by_full_dataset_logical_dependencies"] != 1:
        raise AssertionError("Implication rejection was not accounted for.")


def _quartets_for_sample(
    sample: pd.DataFrame,
    combinations: np.ndarray,
    feature_ids: list[str],
    semantic_representatives: dict[str, str],
    exact_representatives: dict[str, str],
    complement_representatives: dict[str, str],
    full_implication_pairs: set[frozenset[str]],
) -> dict[str, Any]:
    values = sample[feature_ids].to_numpy(dtype=np.uint8).T
    selected = values[combinations]
    signatures = np.sum(selected * (1 << np.arange(4, dtype=np.uint8))[None, :, None], axis=1)
    sorted_signatures = np.sort(signatures, axis=1)
    valid_mask = np.all(np.diff(sorted_signatures, axis=1) == 1, axis=1)
    valid_indices = np.flatnonzero(valid_mask)
    valid_quartets = [
        tuple(feature_ids[index] for index in combinations[quartet_index])
        for quartet_index in valid_indices
    ]

    semantic_keys = {
        tuple(sorted(semantic_representatives[f] for f in quartet)) for quartet in valid_quartets
    }
    dataset_exact_keys = {
        tuple(sorted(exact_representatives[f] for f in quartet)) for quartet in valid_quartets
    }
    complement_keys = {
        tuple(sorted(complement_representatives[f] for f in quartet)) for quartet in valid_quartets
    }
    game_structures: dict[tuple[int, ...], list[tuple[str, ...]]] = defaultdict(list)
    for quartet_index, quartet in zip(valid_indices, valid_quartets):
        game_key = _canonical_game_structure(signatures[quartet_index])
        game_structures[game_key].append(quartet)

    invalid_exact_duplicate_or_complement = 0
    invalid_logical = 0
    invalid_sample_dependency = 0
    invalid_signature_only = 0
    all_pairs = set(full_implication_pairs)
    for index in range(len(feature_ids)):
        a = sample[feature_ids[index]].to_numpy(dtype=bool)
        for other in range(index + 1, len(feature_ids)):
            b = sample[feature_ids[other]].to_numpy(dtype=bool)
            if np.all(~a | b) or np.all(~b | a):
                all_pairs.add(frozenset((feature_ids[index], feature_ids[other])))
    for combo_index in np.flatnonzero(~valid_mask):
        quartet = tuple(feature_ids[index] for index in combinations[combo_index])
        pairs = [frozenset(pair) for pair in itertools.combinations(quartet, 2)]
        if any(exact_representatives[a] == exact_representatives[b] for a, b in itertools.combinations(quartet, 2)):
            invalid_exact_duplicate_or_complement += 1
        elif any(
            complement_representatives[a] == complement_representatives[b]
            for a, b in itertools.combinations(quartet, 2)
        ):
            invalid_exact_duplicate_or_complement += 1
        elif any(pair in full_implication_pairs for pair in pairs):
            invalid_logical += 1
        elif any(pair in all_pairs for pair in pairs):
            invalid_sample_dependency += 1
        else:
            invalid_signature_only += 1

    return {
        "raw_valid_semantic_quartets": len(valid_quartets),
        "valid_after_exact_semantic_handling": len(semantic_keys),
        "valid_after_dataset_exact_duplicate_handling": len(dataset_exact_keys),
        "valid_after_complement_equivalence_handling": len(complement_keys),
        "game_structurally_distinct_valid_quartets": len(game_structures),
        "invalid_rejected_by_exact_duplicate_or_complement_constraint": invalid_exact_duplicate_or_complement,
        "invalid_rejected_by_full_dataset_logical_dependencies": invalid_logical,
        "invalid_rejected_by_sample_observed_dependencies": invalid_sample_dependency,
        "invalid_rejected_by_other_observed_signature_constraints": invalid_signature_only,
        "valid_quartets": [list(quartet) for quartet in valid_quartets],
        "game_structural_classes": [
            {"quartets": [list(quartet) for quartet in quartets]}
            for quartets in game_structures.values()
        ],
        "valid_quartet_family_composition": dict(
            sorted(
                Counter(
                    "+".join(sorted({next(feature["family"] for feature in FEATURES if feature["feature_id"] == feature_id) for feature_id in quartet}))
                    for quartet in valid_quartets
                ).items()
            )
        ),
    }


def _draft_analysis(
    sample: pd.DataFrame,
    valid_quartets: list[tuple[str, ...]],
    structural_keys: dict[tuple[str, ...], tuple[int, ...]],
) -> dict[str, Any]:
    state_to_quartets: dict[tuple[tuple[str, str], ...], set[tuple[str, ...]]] = defaultdict(set)
    for quartet in valid_quartets:
        for player_1_indices in itertools.combinations(range(4), 2):
            owner_by_feature = {
                feature_id: ("player_1" if index in player_1_indices else "player_2")
                for index, feature_id in enumerate(quartet)
            }
            state_to_quartets[()].add(quartet)
            for size in range(1, 4):
                for accepted_features in itertools.combinations(quartet, size):
                    state = tuple(sorted((feature_id, owner_by_feature[feature_id]) for feature_id in accepted_features))
                    state_to_quartets[state].add(quartet)

    state_rows = []
    feature_ids = [feature["feature_id"] for feature in FEATURES]
    for state in state_to_quartets:
        if len(state) == 4:
            continue
        accepted_ids = {feature_id for feature_id, _owner in state}
        owner_counts = Counter(owner for _feature_id, owner in state)
        if any(owner_counts[player] > 2 for player in PLAYERS):
            continue
        consistent = [
            quartet
            for quartet in valid_quartets
            if accepted_ids.issubset(quartet)
            and all(owner_counts[player] <= 2 for player in PLAYERS)
        ]
        if not consistent:
            continue
        structural = {structural_keys[quartet] for quartet in consistent}
        state_rows.append(
            {
                "accepted": [{"feature_id": feature_id, "owner": owner} for feature_id, owner in state],
                "accepted_count": len(state),
                "semantic_hypothesis_count": len(consistent),
                "game_structural_hypothesis_count": len(structural),
            }
        )
    semantic_counts = [row["semantic_hypothesis_count"] for row in state_rows]
    structural_counts = [row["game_structural_hypothesis_count"] for row in state_rows]
    return {
        "extendable_nonterminal_prefix_count": len(state_rows),
        "semantic_minimum": min(semantic_counts) if semantic_counts else None,
        "semantic_median": float(np.median(semantic_counts)) if semantic_counts else None,
        "semantic_exactly_one_fraction": (
            sum(value == 1 for value in semantic_counts) / len(semantic_counts) if semantic_counts else None
        ),
        "semantic_at_most_two_fraction": (
            sum(value <= 2 for value in semantic_counts) / len(semantic_counts) if semantic_counts else None
        ),
        "semantic_count_distribution": dict(sorted(Counter(semantic_counts).items())),
        "structural_minimum": min(structural_counts) if structural_counts else None,
        "structural_median": float(np.median(structural_counts)) if structural_counts else None,
        "structural_exactly_one_fraction": (
            sum(value == 1 for value in structural_counts) / len(structural_counts) if structural_counts else None
        ),
        "structural_at_most_two_fraction": (
            sum(value <= 2 for value in structural_counts) / len(structural_counts) if structural_counts else None
        ),
        "structural_count_distribution": dict(sorted(Counter(structural_counts).items())),
        "states": state_rows,
        "protocol_assumption": "Accepted identities are modeled as an unordered prefix with owner labels; no proposer turn schedule is imposed because none is defined in this experiment brief.",
    }


def run_experiment() -> dict[str, Any]:
    _validate_smarts_semantics()
    _validate_quartet_accounting()
    raw_sha256 = hashlib.sha256(ARCHIVE_PATH.read_bytes()).hexdigest()
    archive_size = ARCHIVE_PATH.stat().st_size
    records, failures, archive_record_count = _source_records()
    entities = pd.DataFrame(records).sort_values("source_id").reset_index(drop=True)
    if entities.empty:
        raise RuntimeError("No QM9 entities were parsed.")
    if entities["source_id"].duplicated().any():
        raise AssertionError("Repeated stable source IDs found.")
    feature_ids = [feature["feature_id"] for feature in FEATURES]
    matrix = entities[["source_id", *feature_ids]].copy()
    if matrix[feature_ids].isna().any().any():
        raise AssertionError("Feature matrix has unhandled missing values.")
    if not all(pd.api.types.is_bool_dtype(matrix[feature_id]) for feature_id in feature_ids):
        raise AssertionError("Feature matrix contains non-boolean feature columns.")
    if not entities["parse_status"].eq("parsed_and_sanitized").all():
        raise AssertionError("Entity manifest includes an unparsed or unsanitized structure.")
    if not entities["original_smiles"].map(bool).all() or not entities["original_inchi"].map(bool).all():
        raise AssertionError("Source SMILES or InChI is missing.")

    registry_rows = []
    for definition in FEATURES:
        values = matrix[definition["feature_id"]].astype(bool)
        true_count = int(values.sum())
        false_count = int((~values).sum())
        row = dict(definition)
        row.update(
            {
                "rdkit_version": rdBase.rdkitVersion,
                "aromaticity_and_sanitization": "RDKit MolFromSmiles sanitization and default aromaticity model.",
                "coverage_count": len(values),
                "missing_count": 0,
                "true_count": true_count,
                "false_count": false_count,
                "prevalence": true_count / len(values),
                "constant_in_population": true_count == 0 or false_count == 0,
                "useful_variance_in_population": true_count > 0 and false_count > 0,
                "eligible_for_gameplay": true_count > 0 and false_count > 0,
                "semantic_key": definition["graph_predicate"],
            }
        )
        registry_rows.append(row)
    registry = pd.DataFrame(registry_rows)
    relationships = _feature_relationships(matrix, registry)
    gameplay_features = [
        feature_id
        for feature_id in feature_ids
        if bool(registry.loc[registry.feature_id == feature_id, "eligible_for_gameplay"].iloc[0])
    ]
    semantic_representatives: dict[str, str] = {}
    semantic_rep_by_id: dict[str, str] = {}
    for feature in FEATURES:
        feature_id = feature["feature_id"]
        semantic_rep_by_id[feature_id] = semantic_representatives.setdefault(
            feature["graph_predicate"], feature_id
        )
    exact_representatives, complement_representatives = _classify_feature_columns(matrix, gameplay_features)
    combinations = np.asarray(
        list(itertools.combinations(range(len(gameplay_features)), 4)), dtype=np.int16
    ).reshape((-1, 4))
    if len(combinations) != math.comb(len(gameplay_features), 4):
        raise AssertionError("Quartet combination count mismatch.")
    full_implication_pairs = {
        frozenset((item["source"], item["target"]))
        for item in relationships["full_dataset_implications"]
    }
    rng = np.random.default_rng(PUBLIC_SAMPLE_SEED)
    sample_indices = [rng.choice(len(matrix), size=SAMPLE_SIZE, replace=False) for _ in range(SAMPLE_COUNT)]
    reproducibility_rng = np.random.default_rng(PUBLIC_SAMPLE_SEED)
    reproducibility_sample = reproducibility_rng.choice(len(matrix), size=SAMPLE_SIZE, replace=False)
    if not np.array_equal(sample_indices[0], reproducibility_sample):
        raise AssertionError("Deterministic sample reproducibility check failed.")

    samples: list[dict[str, Any]] = []
    valid_sample_details: list[dict[str, Any]] = []
    for sample_number, indices in enumerate(sample_indices):
        sample = matrix.iloc[indices].reset_index(drop=True)
        quartet_result = _quartets_for_sample(
            sample,
            combinations,
            gameplay_features,
            semantic_rep_by_id,
            exact_representatives,
            complement_representatives,
            full_implication_pairs,
        )
        valid_quartets = [tuple(quartet) for quartet in quartet_result["valid_quartets"]]
        structural_keys = {
            tuple(quartet): _canonical_game_structure(
                np.sum(
                    sample[list(quartet)].to_numpy(dtype=np.uint8)
                    * (1 << np.arange(4, dtype=np.uint8))[None, :],
                    axis=1,
                )
            )
            for quartet in valid_quartets
        }
        draft = _draft_analysis(sample, valid_quartets, structural_keys)
        sample_result = {
            "sample_index": sample_number,
            "selected_source_ids": sample["source_id"].tolist(),
            **{key: value for key, value in quartet_result.items() if key not in {"valid_quartets", "game_structural_classes"}},
            "valid_quartets": quartet_result["valid_quartets"],
            "game_structural_classes": quartet_result["game_structural_classes"],
            "draft_analysis": draft,
        }
        samples.append(sample_result)
        if valid_quartets:
            valid_sample_details.append(sample_result)
    sample_valid_counts = [sample["raw_valid_semantic_quartets"] for sample in samples]
    count_fields = (
        "raw_valid_semantic_quartets",
        "valid_after_exact_semantic_handling",
        "valid_after_dataset_exact_duplicate_handling",
        "valid_after_complement_equivalence_handling",
        "game_structurally_distinct_valid_quartets",
        "invalid_rejected_by_exact_duplicate_or_complement_constraint",
        "invalid_rejected_by_full_dataset_logical_dependencies",
        "invalid_rejected_by_sample_observed_dependencies",
        "invalid_rejected_by_other_observed_signature_constraints",
    )
    sample_count_totals = {
        field: sum(int(sample[field]) for sample in samples) for field in count_fields
    }
    family_totals: Counter[str] = Counter()
    for sample in samples:
        family_totals.update(sample["valid_quartet_family_composition"])

    repeated_canonical = entities.groupby("canonical_isomeric_smiles")["source_id"].agg(list)
    repeated_canonical = {
        smiles: source_ids for smiles, source_ids in repeated_canonical.items() if len(source_ids) > 1
    }
    stereo_groups = entities.groupby("canonical_smiles")["canonical_isomeric_smiles"].nunique()
    stereo_ambiguous_graphs = int((stereo_groups > 1).sum())

    result: dict[str, Any] = {
        "experiment_status": "EXECUTED",
        "dataset": {
            "source_name": "QM9 original XYZ archive",
            "source_version": "Original QM9 release described in Ramakrishnan et al. (2014); archive checksum pinned below.",
            "original_source_url": "https://quantum-machine.org/datasets/",
            "download_url": ARCHIVE_URL,
            "figshare_file_id": 3195389,
            "original_archive_filename": "dsgdb9nsd.xyz.tar.bz2",
            "archive_path": ARCHIVE_PATH.name,
            "archive_size_bytes": archive_size,
            "archive_sha256": raw_sha256,
            "archive_record_count": archive_record_count,
            "parsed_entity_count": len(entities),
            "excluded_record_count": len(failures),
            "excluded_records": failures,
            "repeated_source_id_count": 0,
            "repeated_canonical_structure_count": len(repeated_canonical),
            "repeated_canonical_structures": repeated_canonical,
            "nonisomeric_graphs_with_multiple_isomeric_smiles": stereo_ambiguous_graphs,
            "source_publication": {
                "citation": "Ramakrishnan et al., Quantum chemistry structures and properties of 134 kilo molecules, Scientific Data 1 (2014).",
                "doi": "10.1038/sdata.2014.22",
                "article_license": "CC BY-NC-SA 4.0 per Crossref metadata; this applies to the article and is not evidence of the separate raw-archive license.",
            },
            "source_license_note": "The accessible Figshare download response did not expose a license for the raw archive. The article is indexed as CC BY-NC-SA 4.0, but that must not be assumed to license the archive. Verify archive-specific reuse and redistribution terms before redistributing it.",
            "transformations": [
                "Read each XYZ member sequentially from the original tar.bz2 archive.",
                "Use the source record's first SMILES and InChI fields; preserve source IDs independently.",
                "Sanitize source SMILES with RDKit and produce canonical isomeric and non-isomeric SMILES.",
                "Do not merge records by canonical structure.",
            ],
        },
        "software": {
            "python": __import__("sys").version.split()[0],
            "rdkit": rdBase.rdkitVersion,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "feature_ids": feature_ids,
        "gameplay_feature_ids": gameplay_features,
        "feature_registry": registry_rows,
        "feature_relationships": relationships,
        "definition_guaranteed_implications": relationships["definition_guaranteed_implications"],
        "qm9_domain_identities": relationships["qm9_domain_identities"],
        "sample_design": {
            "sample_count": SAMPLE_COUNT,
            "sample_size": SAMPLE_SIZE,
            "seed": PUBLIC_SAMPLE_SEED,
            "sampling": "One deterministic NumPy Generator; every sample is a uniform sample without replacement from the successfully normalized QM9 population.",
            "replacement_of_failed_samples": False,
            "reproducibility_check": "Passed: first sample exactly reproduced from a new generator with the same seed.",
        },
        "validation_checks": {
            "smarts_positive_negative_examples": "passed",
            "signature_bijection_acceptance": "passed",
            "implication_invalidity_without_feature_collapse": "passed",
            "global_bit_complement_structural_equivalence": "passed",
            "binary_matrix_and_missing_value_assertions": "passed",
            "reproducible_sampling": "passed",
        },
        "sample_summary": {
            "sample_count": len(samples),
            "samples_with_valid_quartet": sum(count > 0 for count in sample_valid_counts),
            "sample_fraction_with_valid_quartet": sum(count > 0 for count in sample_valid_counts) / len(samples),
            "max_raw_valid_quartets": max(sample_valid_counts, default=0),
            "raw_valid_quartet_count_distribution": dict(sorted(Counter(sample_valid_counts).items())),
            "samples_with_game_structural_class": sum(
                sample["game_structurally_distinct_valid_quartets"] > 0 for sample in samples
            ),
            "sum_across_samples_by_quartet_accounting_stage": sample_count_totals,
            "valid_quartets_by_feature_family_combination": dict(sorted(family_totals.items())),
        },
        "samples": samples,
        "draft_summary": {
            "samples_with_draft_states": len(valid_sample_details),
            "semantic_state_count_distribution": dict(
                sorted(
                    Counter(
                        state["semantic_hypothesis_count"]
                        for sample in valid_sample_details
                        for state in sample["draft_analysis"]["states"]
                    ).items()
                )
            ),
            "structural_state_count_distribution": dict(
                sorted(
                    Counter(
                        state["game_structural_hypothesis_count"]
                        for sample in valid_sample_details
                        for state in sample["draft_analysis"]["states"]
                    ).items()
                )
            ),
            "all_prefix_states": sum(
                sample["draft_analysis"]["extendable_nonterminal_prefix_count"]
                for sample in valid_sample_details
            ),
        },
        "scientific_limitations": [
            "QM9 structures and quantum properties are computationally generated and are not an unbiased sample of all real-world molecules.",
            "SMARTS predicates are operational graph definitions; chemical classes may be broader than the deliberately narrow predicates used here.",
            "Full-dataset implication detection is empirical over QM9 and is not automatically a universal chemical law.",
            "Initial quartet ambiguity is not sufficient if ownership-aware draft prefixes reduce the remaining hypotheses.",
        ],
    }
    _write_outputs(entities, matrix, registry, result)
    return result


def _write_outputs(
    entities: pd.DataFrame, matrix: pd.DataFrame, registry: pd.DataFrame, result: dict[str, Any]
) -> None:
    entities.to_csv(EXPERIMENT_DIR / "entity_manifest.csv", index=False)
    matrix.to_csv(EXPERIMENT_DIR / "feature_matrix.csv", index=False)
    registry.to_csv(EXPERIMENT_DIR / "feature_registry.csv", index=False)
    (EXPERIMENT_DIR / "playable_candidate_features.json").write_text(
        json.dumps(
            {
                "candidate_feature_ids": result["gameplay_feature_ids"],
                "eligibility_rule": "Scientifically valid feature with both true and false values in the successfully normalized full QM9 population; no correlation-only exclusion.",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (EXPERIMENT_DIR / "preprocessing_config.json").write_text(
        json.dumps(
            {
                "archive": ARCHIVE_PATH.name,
                "archive_url": ARCHIVE_URL,
                "feature_registry_order": [feature["feature_id"] for feature in FEATURES],
                "public_sample_seed": PUBLIC_SAMPLE_SEED,
                "sample_count": SAMPLE_COUNT,
                "sample_size": SAMPLE_SIZE,
                "hydrogen_semantics": "Feature contains_hydrogen includes implicit and explicit hydrogens; manifest records explicit graph hydrogen nodes and implicit hydrogen count separately.",
                "missing_value_policy": "Source parse or sanitization failures are explicitly excluded with a reason; no feature missingness is imputed as false.",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (EXPERIMENT_DIR / "dataset_provenance.json").write_text(
        json.dumps(result["dataset"], indent=2, sort_keys=True), encoding="utf-8"
    )
    (EXPERIMENT_DIR / "validation_report.json").write_text(
        json.dumps(
            {
                "feature_relationships": result["feature_relationships"],
                "feature_counts": {
                    "scientifically_valid": sum(item["scientifically_valid"] for item in result["feature_registry"]),
                    "gameplay_eligible": len(result["gameplay_feature_ids"]),
                    "constant": sum(item["constant_in_population"] for item in result["feature_registry"]),
                },
                "sample_summary": result["sample_summary"],
                "draft_summary": result["draft_summary"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (EXPERIMENT_DIR / "results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    (EXPERIMENT_DIR / "REPORT.md").write_text(_build_report(result), encoding="utf-8")


def _build_report(result: dict[str, Any]) -> str:
    dataset = result["dataset"]
    summary = result["sample_summary"]
    draft = result["draft_summary"]
    relationships = result["feature_relationships"]
    sections = [
        "# QM9 Hidden-Feature Quarto Experiment",
        "",
        "## Scope and status",
        "",
        "This is an offline, reproducible feasibility experiment. It did not modify the existing game engine, benchmark, frozen dataset, or prior experiment files, and it did not start a live game or create a hidden entity-to-piece mapping.",
        "",
        "## Dataset provenance and normalization",
        "",
        f"- Original QM9 source page: {dataset['original_source_url']}",
        f"- Source: {dataset['source_name']}; file ID {dataset['figshare_file_id']} via {dataset['download_url']}.",
        f"- Dataset version: {dataset['source_version']}",
        f"- Source publication: {dataset['source_publication']['citation']} DOI `{dataset['source_publication']['doi']}`.",
        f"- Publication license: {dataset['source_publication']['article_license']}",
        f"- Preserved archive: `{dataset['original_archive_filename']}` ({dataset['archive_size_bytes']:,} bytes).",
        f"- SHA-256: `{dataset['archive_sha256']}`.",
        f"- XYZ records in archive: {dataset['archive_record_count']:,}.",
        f"- Successfully parsed and sanitized entities: {dataset['parsed_entity_count']:,}.",
        f"- Excluded records: {dataset['excluded_record_count']:,}.",
        f"- Repeated source IDs: {dataset['repeated_source_id_count']}.",
        f"- Repeated canonical isomeric structures: {dataset['repeated_canonical_structure_count']}.",
        f"- Non-isomeric graphs with multiple isomeric SMILES: {dataset['nonisomeric_graphs_with_multiple_isomeric_smiles']}.",
        f"- License and redistribution terms: {dataset['source_license_note']}",
        "",
        "Source identity is preserved independently from canonical graph identity. Records are not merged by canonical SMILES. Canonical isomeric and non-isomeric SMILES, molecular formula, heavy atom count, formal charge, source SMILES/InChI, and explicit/implicit hydrogen counts are included in the entity manifest.",
        "",
        "## Scientific feature registry",
        "",
        f"- Scientifically valid feature definitions: {len(result['feature_registry'])}.",
        f"- Gameplay-eligible features with population variance: {len(result['gameplay_feature_ids'])}.",
        f"- Constant features retained in the scientific registry: {sum(item['constant_in_population'] for item in result['feature_registry'])}.",
        f"- Exact semantic duplicate groups: {len(relationships['exact_semantic_duplicates'])}.",
        f"- Dataset-level exact duplicate pairs: {len(relationships['dataset_exact_duplicates'])}.",
        f"- Dataset-level complement pairs: {len(relationships['dataset_complements'])}.",
        "",
        "The complete machine-readable registry is in `feature_registry.csv`. It documents graph predicates, RDKit version, sanitization/aromaticity assumptions, hydrogen semantics, prevalence, dependencies, and gameplay eligibility. Correlation is descriptive and is not used as an exclusion criterion.",
        "",
        "## Feature dependencies and associations",
        "",
        f"- Definition-guaranteed or QM9-domain implications recorded: {len(result['definition_guaranteed_implications'])}.",
        f"- Empirical implications observed over the full normalized QM9 population: {len(relationships['full_dataset_implications'])}.",
        f"- Pairwise phi associations: {len(relationships['pairwise_phi_associations'])}.",
        "",
        "Implication constrains validity but does not collapse feature identities. Full-population implication is labeled empirical unless guaranteed by the predicate definitions or QM9 domain. Dataset-level complements and exact duplicates are accounted for separately.",
        "",
        "## Random sample and quartet results",
        "",
        f"- Uniform random samples: {result['sample_design']['sample_count']:,} of 16 entities each, without replacement.",
        f"- Public seed: {result['sample_design']['seed']}.",
        f"- Samples admitting at least one valid quartet: {summary['samples_with_valid_quartet']:,}/{summary['sample_count']:,} ({summary['sample_fraction_with_valid_quartet']:.3%}).",
        f"- Maximum raw valid semantic quartets in one sample: {summary['max_raw_valid_quartets']}.",
        f"- Sum of raw valid semantic quartets across samples: {summary['sum_across_samples_by_quartet_accounting_stage']['raw_valid_semantic_quartets']:,}.",
        f"- Sum after exact semantic duplicate handling: {summary['sum_across_samples_by_quartet_accounting_stage']['valid_after_exact_semantic_handling']:,}.",
        f"- Sum after dataset-level exact duplicate handling: {summary['sum_across_samples_by_quartet_accounting_stage']['valid_after_dataset_exact_duplicate_handling']:,}.",
        f"- Sum after complement-equivalence handling: {summary['sum_across_samples_by_quartet_accounting_stage']['valid_after_complement_equivalence_handling']:,}.",
        f"- Sum of game-structurally distinct valid quartets across samples: {summary['sum_across_samples_by_quartet_accounting_stage']['game_structurally_distinct_valid_quartets']:,}.",
        f"- Samples with any game-structural class: {summary['samples_with_game_structural_class']:,}.",
        "",
        "Quartet counts and rejection counts are reported by sample in `results.json`; the raw-quartet-count distribution is in `validation_report.json`. A quartet is valid only when all 16 signatures occur exactly once. Game-structural equivalence canonicalizes entity-to-signature mappings under bit permutations and independent global bit complements.",
        "",
        "### Quartet rejection accounting (summed over samples)",
        "",
    ]
    for field in (
        "invalid_rejected_by_exact_duplicate_or_complement_constraint",
        "invalid_rejected_by_full_dataset_logical_dependencies",
        "invalid_rejected_by_sample_observed_dependencies",
        "invalid_rejected_by_other_observed_signature_constraints",
    ):
        sections.append(f"- `{field}`: {summary['sum_across_samples_by_quartet_accounting_stage'][field]:,}.")
    sections.extend(
        [
            "",
            "## Draft-stage ambiguity",
            "",
            f"- Successful samples with draft prefixes to analyze: {draft['samples_with_draft_states']:,}.",
            f"- Extendable nonterminal ownership-labeled prefixes analyzed: {draft['all_prefix_states']:,}.",
            f"- Semantic remaining-hypothesis distribution: `{json.dumps(draft['semantic_state_count_distribution'], sort_keys=True)}`.",
            f"- Game-structural remaining-hypothesis distribution: `{json.dumps(draft['structural_state_count_distribution'], sort_keys=True)}`.",
            "",
            "The draft state model treats accepted feature identities as an unordered prefix labeled by owner and considers every assignment with two final features per player. No proposer turn schedule is imposed because none is defined in this experiment brief. Counts are hypotheses, not entropy. No ambiguity threshold is imposed.",
            "",
            "## Suitability, limitations, and next step",
            "",
            "QM9 is a plausible first molecular domain for controlled, graph-defined feature experiments, but it is a computed, highly selected chemical-space dataset rather than a representative sample of all real molecules. A live benchmark should not be claimed based only on the existence of valid quartets; the measured draft ambiguity distribution and source-license status must be reviewed first.",
            "",
            "Known limitations include RDKit's chosen aromaticity and sanitization conventions, deliberately narrow SMARTS definitions, empirical rather than universal full-dataset implications, QM9 sampling bias, and the unverified license/redistribution terms. The next step is to verify the authoritative Figshare reuse terms, review feature definitions, and assess whether the measured random-sample and draft distributions meet a pre-registered benchmark criterion.",
            "",
            "## Reproducibility",
            "",
            f"- Python {result['software']['python']}; RDKit {result['software']['rdkit']}; NumPy {result['software']['numpy']}; pandas {result['software']['pandas']}.",
            f"- Sample reproducibility: {result['sample_design']['reproducibility_check']}",
            "- Outputs are confined to `experiments/qm9_quarto/`.",
            "- No game, tournament, engine state, or hidden piece mapping was used.",
            "",
        ]
    )
    return "\n".join(sections)


def main() -> None:
    result = run_experiment()
    print(json.dumps(result["sample_summary"], indent=2, sort_keys=True))
    print(json.dumps(result["draft_summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
