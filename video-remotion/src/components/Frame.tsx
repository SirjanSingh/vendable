// Every scene's content sits in this box: full height, vertically centred,
// inside the horizontal safe margin. This is the fix for the defect that made
// the first cut look like a slide deck — content pinned to the top-left with
// `padding: 96px 140px` and the bottom half of the frame left empty.
import React from "react";
import { AbsoluteFill } from "remotion";

import { theme } from "../theme";

export const Frame: React.FC<{
  children: React.ReactNode;
  justify?: React.CSSProperties["justifyContent"];
  style?: React.CSSProperties;
}> = ({ children, justify = "center", style }) => (
  <AbsoluteFill
    style={{
      // Explicit, not inherited from AbsoluteFill's inset. Without a definite
      // width here every child sized itself to min-content and the column
      // overflowed the frame vertically.
      width: 1920,
      height: 1080,
      paddingLeft: theme.layout.marginX,
      paddingRight: theme.layout.marginX,
      boxSizing: "border-box",
      display: "flex",
      flexDirection: "column",
      justifyContent: justify,
      // Must stay "stretch". With "flex-start" each child is sized to
      // fit-content, which inside an absolutely-positioned flex container
      // resolves to MIN-content: every paragraph collapsed to the width of its
      // longest word and ran off the bottom of the frame.
      alignItems: "stretch",
      color: theme.colors.text,
      fontFamily: theme.fonts.sans,
      ...style,
    }}
  >
    {children}
  </AbsoluteFill>
);
