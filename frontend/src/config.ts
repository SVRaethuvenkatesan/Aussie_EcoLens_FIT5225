export const CONFIG = {
  // Cognito
  USER_POOL_ID: "us-east-1_YIG3u62sM",
  CLIENT_ID: "3d4m3g86gj50c2erc4vts7aig4",
  REGION: "us-east-1",
  DOMAIN: "us-east-1yig3u62sm.auth.us-east-1.amazoncognito.com",

  // API Gateway
  API_URL: "https://hp92cdlvcc.execute-api.us-east-1.amazonaws.com/prod",

  // Auth URLs
  getLoginUrl: (origin: string) =>
    `https://us-east-1yig3u62sm.auth.us-east-1.amazoncognito.com/login?client_id=3d4m3g86gj50c2erc4vts7aig4&response_type=token&scope=email+openid+profile&redirect_uri=${encodeURIComponent(
      origin + "/"
    )}`,
  getLogoutUrl: (origin: string) =>
    `https://us-east-1yig3u62sm.auth.us-east-1.amazoncognito.com/logout?client_id=3d4m3g86gj50c2erc4vts7aig4&logout_uri=${encodeURIComponent(
      origin
    )}`,
};
