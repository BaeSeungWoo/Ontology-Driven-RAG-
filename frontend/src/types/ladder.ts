export type LadderContact = {
  kind: "contact";
  addr: string;
  label: string;
  description: string;
  neg: boolean;
};

export type LadderNode = LadderContact | {
  kind: "series" | "parallel";
  children: LadderNode[];
};

export type LadderDiagram = {
  nblock: string;
  instructions: string[];
} & ({ status: "supported"; logic: LadderNode; coil: LadderContact } | { status: "unsupported" });
