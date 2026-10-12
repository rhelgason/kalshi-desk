import Avatar from "@/components/Avatar";
import { SPRITES } from "@/lib/sprites";

/** Design sheet for the pixel portraits (not linked from the menu). */
export default function Sprites() {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
      {Object.keys(SPRITES).map((k) => (
        <div key={k} style={{ textAlign: "center", fontSize: 11 }}>
          <div style={{ background: "#2a2440", padding: 8 }}><Avatar k={k} size={96} /></div>
          {k}
        </div>
      ))}
    </div>
  );
}
