import type { ImgHTMLAttributes } from "react";
import { branding } from "./runtime";

type Props = ImgHTMLAttributes<HTMLImageElement> & { src: string };

/**
 * `<img>` that honours the deployment's runtime logo override.
 *
 * Call sites keep passing their built-in asset path, so an OEM logo is a
 * single settings write rather than a rebuild. `object-fit: contain` keeps a
 * square mark from being stretched when it lands in a horizontal slot.
 */
export function AppLogo({ src, style, ...rest }: Props) {
  const override = branding().logo_url;
  return (
    <img
      src={override ?? src}
      style={{ objectFit: "contain", ...style }}
      {...rest}
    />
  );
}

export default AppLogo;
