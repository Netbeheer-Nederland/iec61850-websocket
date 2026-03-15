# FT6: Receive status updates from the Connected Party using unbuffered reporting service

The following negative test case variations can be considered (Optional):

1. The URCB cannot be configured because the SetURCBValues request is sent with an invalid URCB reference (Optional)1.
The URCB cannot be configured because the SetURCBValues request is sent with an invalid parameter value (Optional)1. The
                                                                                                                     URCB
                                                                                                                     cannot
                                                                                                                     be
                                                                                                                     enabled
                                                                                                                     because
                                                                                                                     it
                                                                                                                     has
                                                                                                                     already
                                                                                                                     be
                                                                                                                     enabled
                                                                                                                     by
                                                                                                                     another
                                                                                                                     ACSI
                                                                                                                     client
                                                                                                                     instance (
                                                                                                                     Optional)

**Conclusions:**

1. Using the “SetURCBValues” service the URCB can be configured and enable to receive status values when changes are
   made.
1. A valid URCB reference must be used to correctly use the service.
1. The test case **passed.**
