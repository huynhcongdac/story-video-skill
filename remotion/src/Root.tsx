import React from "react";
import { Composition } from "remotion";
import { Story } from "./Story";
import timeline from "./timeline.json";

export const Root: React.FC = () => (
  <Composition id="Story" component={Story} width={1080} height={1920} fps={timeline.fps}
    durationInFrames={timeline.durationInFrames} />
);
